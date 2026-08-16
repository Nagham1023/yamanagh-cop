"""Orchestrator's server lifecycle (PRD 2/5) — split out of orchestrator.py,
which grew past the 150-line house cap once PRD 5's tunnel wiring landed.
A mixin, not a standalone class: reaches into `self.watchdog`, `self.trace`,
`self.server`, all of which `Orchestrator.__init__` sets up — this file
only exists to keep `orchestrator.py` under the cap, same shape as
`orchestrator_turn.py`'s split for the brain-driven turn.
"""

from __future__ import annotations

import os
import threading

from .tools.cloudflare_tunnel import start_cloudflare_tunnel
from .tools.tunnel import stop_tunnel
from .tools.tunnel_start import start_tunnel


class ServerLifecycleMixin:
    def _persist_watchdog_state(self) -> None:
        """PRD 15 (ch. 8.4): a real, structured snapshot — not just the
        state-machine's phase name — logged the moment `Watchdog.check()`
        finds a stale heartbeat, before `controlled_shutdown` ends the
        process. `sorted()` needs the `[col, row]` list form, not bare
        `Position` objects (no `__lt__`). No auto-resume reads this back;
        that's a deliberately larger, separate feature (README §5)."""
        self.trace.log(
            "watchdog_persist_state",
            state=self.state_machine.state,
            own_pos=[self.game_state.own_pos.col, self.game_state.own_pos.row],
            target_pos=[self.game_state.target_pos.col, self.game_state.target_pos.row],
            barriers_placed=sorted([p.col, p.row] for p in self.game_state.barriers.placed),
            steps_taken=self.game_state.steps_taken,
        )

    def _watch_loop(self, poll_interval_seconds: float) -> None:
        """Background daemon thread: rule 7 says "run" a watchdog, not merely
        construct one. `check()` already runs `persist_state`/`controlled_shutdown`
        on staleness; this loop's only remaining job is to end the frozen
        process once that has happened, so the OS-level crash/hang is real.

        `Event.wait(timeout)` doubles as the poll sleep and the stop signal:
        it returns `True` (and this loop exits) the instant
        `stop_watchdog_monitor` sets the event, or `False` after a normal
        `poll_interval_seconds` timeout — never a plain `time.sleep`, which
        can't be woken early."""
        while not self._watchdog_stop_event.wait(poll_interval_seconds):
            if self.watchdog.check() == "SHUTDOWN":
                os._exit(1)

    def _start_watchdog_monitor(self, poll_interval_seconds: float = 1.0) -> None:
        threading.Thread(
            target=self._watch_loop, args=(poll_interval_seconds,), daemon=True
        ).start()

    def stop_tunnel_if_running(self) -> None:
        """Explicit, main-thread-callable teardown for the tunnel
        `run_as_server` starts — needed because that method itself runs on
        a `daemon=True` thread blocking inside `self.server.run(...)`,
        which never returns under normal operation: the whole process
        instead exits once the client-driven match (on the *main* thread)
        finishes. Daemon threads don't get to run their own pending
        `finally` blocks when the interpreter exits that way, so
        `run_as_server`'s own `finally: stop_tunnel_if_running()` never
        actually fires in that path. Found live: the `ngrok` child process
        was orphaned every real match this session, left routing to a now
        -dead local server (ngrok's own `ERR_NGROK_8012`) and permanently
        blocking every later launch (`ERR_NGROK_334`, "already online")
        until manually killed. `cli_peer_match_body.py::run_match_body`
        calls this on the main thread, right before the process is
        allowed to exit. Idempotent — safe with no tunnel ever started, or
        already stopped."""
        if self.tunnel is not None:
            stop_tunnel(self.tunnel)
            self.tunnel = None

    def stop_watchdog_monitor(self) -> None:
        """Signals `_watch_loop` to exit on its next wait. Rule 7 means a
        *live* match's watchdog must keep running unconditionally — this is
        for an orchestrator that is genuinely done, not a way to silence an
        active one. A real deployed peer never needs to call this (its own
        process exit takes the daemon thread with it); it exists so a test
        harness that constructs many orchestrators in one shared process
        can stop each one's monitor cleanly, rather than leaking a thread
        that eventually calls a real `os._exit(1)` on staleness long after
        the test that created it has finished. Idempotent — safe even if
        the monitor was never started."""
        self._watchdog_stop_event.set()

    def run_as_server(
        self,
        host: str | None = None,
        port: int = 8800,
        use_tunnel: bool = False,
        ngrok_domain: str | None = None,
        tunnel_provider: str = "ngrok",
    ) -> None:
        """Start listening — blocking, meant to be this process's main loop.

        `host` defaults to `0.0.0.0` when `use_tunnel=True`, `127.0.0.1`
        otherwise — the book's own minimal FastMCP example (ch. 2.3) binds
        `0.0.0.0` specifically "so a tunnel can expose it publicly"
        (PRD-5-cloud-exposure.md Design Question 5). `use_tunnel` is
        opt-in and additive: every existing caller either passes `host`
        explicitly or leaves `use_tunnel` at its default `False`, resolving
        identically to before this parameter existed.

        `ngrok_domain`: a free account's one reserved static domain
        (`tools/tunnel.py::start_tunnel`'s own docstring has the full
        reasoning) — keeps the public URL stable across restarts instead
        of a fresh random one every time. Ignored under `tunnel_provider=
        "cloudflare"` (a Cloudflare Quick Tunnel has no equivalent —
        `tools/cloudflare_tunnel.py`'s own docstring covers why) and
        whenever `use_tunnel=False`.

        `tunnel_provider`: `"ngrok"` (default, unchanged behavior) or
        `"cloudflare"` — tried as an alternative once ngrok's free-tier
        connection-rate cap was diagnosed as a real match's round-26/27
        failure, a request-volume problem rather than a code bug either
        peer's own client had."""
        host = host or ("0.0.0.0" if use_tunnel else "127.0.0.1")
        self.trace.log("server_starting", host=host, port=port)
        self._start_watchdog_monitor()
        if not use_tunnel:
            self.tunnel = None
        elif tunnel_provider == "cloudflare":
            self.tunnel = start_cloudflare_tunnel(port, log_path="logs/cloudflare_tunnel.log")
        else:
            self.tunnel = start_tunnel(port, domain=ngrok_domain, log_path="logs/ngrok_tunnel.log")
        if self.tunnel is not None:
            self.trace.log("tunnel_started", public_url=self.tunnel.public_url, provider=tunnel_provider)
            # Console, not just the trace log — a reserved ngrok domain is
            # known in advance, but a Cloudflare Quick Tunnel URL is fresh
            # and random every single launch (tools/cloudflare_tunnel.py's
            # own docstring), so this is the only way to actually see it in
            # time to relay it to the opponent before the match starts.
            # flush=True: found live — stdout is fully block-buffered
            # (not line-buffered) whenever it isn't a real TTY, e.g.
            # redirected to a file/pipe, so an unflushed print here could
            # sit invisible in the buffer for the whole match instead of
            # showing up in time to actually relay the URL.
            print(f"[tunnel] {tunnel_provider} public URL: {self.tunnel.public_url}", flush=True)
        try:
            self.server.run(transport="http", host=host, port=port, show_banner=False)
        finally:
            # A safety net for the case where `self.server.run` itself
            # returns/raises (e.g. a real crash) — the normal-shutdown
            # path is `stop_tunnel_if_running`'s own docstring above.
            self.stop_tunnel_if_running()
