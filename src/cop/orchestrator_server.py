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
import time

from .tools.tunnel import start_tunnel, stop_tunnel


class ServerLifecycleMixin:
    def _watch_loop(self, poll_interval_seconds: float) -> None:
        """Background daemon thread: rule 7 says "run" a watchdog, not merely
        construct one. `check()` already runs `persist_state`/`controlled_shutdown`
        on staleness; this loop's only remaining job is to end the frozen
        process once that has happened, so the OS-level crash/hang is real."""
        while True:
            time.sleep(poll_interval_seconds)
            if self.watchdog.check() == "SHUTDOWN":
                os._exit(1)

    def _start_watchdog_monitor(self, poll_interval_seconds: float = 1.0) -> None:
        threading.Thread(
            target=self._watch_loop, args=(poll_interval_seconds,), daemon=True
        ).start()

    def run_as_server(self, host: str | None = None, port: int = 8800, use_tunnel: bool = False) -> None:
        """Start listening — blocking, meant to be this process's main loop.

        `host` defaults to `0.0.0.0` when `use_tunnel=True`, `127.0.0.1`
        otherwise — the book's own minimal FastMCP example (ch. 2.3) binds
        `0.0.0.0` specifically "so a tunnel can expose it publicly"
        (PRD-5-cloud-exposure.md Design Question 5). `use_tunnel` is
        opt-in and additive: every existing caller either passes `host`
        explicitly or leaves `use_tunnel` at its default `False`, resolving
        identically to before this parameter existed.
        """
        host = host or ("0.0.0.0" if use_tunnel else "127.0.0.1")
        self.trace.log("server_starting", host=host, port=port)
        self._start_watchdog_monitor()
        tunnel = start_tunnel(port) if use_tunnel else None
        if tunnel is not None:
            self.trace.log("tunnel_started", public_url=tunnel.public_url)
        try:
            self.server.run(transport="http", host=host, port=port, show_banner=False)
        finally:
            if tunnel is not None:
                stop_tunnel(tunnel)
