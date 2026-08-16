"""`run_match_body` — split out of `cli_peer.py`, which grew past the
150-line house cap once the post-match grace period landed. The one
sequence both `run_peer` entry points share: server up, negotiate
Step-0, play, report, then a bounded wait before the process (and its
daemon server thread) is allowed to exit.
"""

from __future__ import annotations

import asyncio
import threading

from .domain.scoring import score_outcome
from .orchestrator import Orchestrator
from .shared.config import GameConfig
from .shared.private_config import PrivateConfig
from .shared.promotion_guard import require_fresh_promotion_report_for_counted_game

_SERVER_STARTUP_GRACE_SECONDS = 0.5
# cloudflared is much slower to report a public URL than ngrok — confirmed
# empirically (tools/cloudflare_tunnel.py's own docstring), ~5s to the URL
# line and several more before its connectivity pre-checks finish, all of
# it blocking run_as_server's own background thread *before* self.server.run
# is ever reached. The plain 0.5s grace above would let this thread race
# ahead to Step-0/play_game while the local port isn't listening yet.
_CLOUDFLARE_SERVER_STARTUP_GRACE_SECONDS = 15.0
# Robustness pacing cap (I6 doesn't apply — same category as this file's
# own _SERVER_STARTUP_GRACE_SECONDS), not a game-rule quantity: an upper
# bound on the heartbeat interval `_sleep_with_heartbeats` actually uses —
# see its own docstring for why the real interval is derived from the
# configured watchdog threshold instead of just this constant alone.
_GRACE_HEARTBEAT_INTERVAL_CAP_SECONDS = 5.0


async def _sleep_with_heartbeats(orchestrator: Orchestrator, total_seconds: float) -> None:
    """Sleeps `total_seconds`, heartbeating the watchdog periodically along
    the way instead of one bare `asyncio.sleep`. The real bug this closes:
    `watchdog_threshold_seconds` (config, negotiated — e.g. 60s in the
    real shared config) and `post_match_grace_seconds` (private, per-team
    — also 60s by this repo's own default) can genuinely coincide, and
    the watchdog's own clock starts counting from the *last real
    heartbeat*, which happens well before this deliberate wait even
    begins — found live: the watchdog fired mid-grace-period, calling
    `os._exit(1)` (`orchestrator_server.py::_watch_loop`), which skips
    every pending `finally` block, silently undoing `run_match_body`'s
    own tunnel/connection cleanup below. A deliberate idle wait this side
    chose to take is not the frozen-process condition rule 7's watchdog
    exists to catch.

    The interval is at most half the *actual* configured
    `watchdog_threshold_seconds`, not just a fixed constant — correct
    regardless of how that negotiated value and `post_match_grace_seconds`
    happen to relate, not only for today's coincidental 60/60 default."""
    interval = min(
        _GRACE_HEARTBEAT_INTERVAL_CAP_SECONDS, orchestrator.config.watchdog_threshold_seconds / 2
    )
    elapsed = 0.0
    while elapsed < total_seconds:
        chunk = min(interval, total_seconds - elapsed)
        await asyncio.sleep(chunk)
        elapsed += chunk
        orchestrator.watchdog.heartbeat()


async def run_match_body(
    orchestrator: Orchestrator,
    private_config: PrivateConfig,
    config: GameConfig,
    *,
    counted: bool,
    use_tunnel: bool,
    ngrok_domain: str | None = None,
    tunnel_provider: str = "ngrok",
) -> Orchestrator:
    """Server up, negotiate Step-0, play, report — the sequence both
    `run_peer` entry points share. PRD 13: refuses a counted game against
    `RLCopBrain` with no current promotion report, before the server
    thread even starts. Sequence is unconditional regardless of
    `initiate_step0` — confirmed by reading `orchestrator_turn.py::take_turn`
    before designing this: both sides always drive their *own* turns,
    "initiator" only ever matters for Step-0."""
    require_fresh_promotion_report_for_counted_game(orchestrator.brain, counted=counted)

    threading.Thread(
        target=orchestrator.run_as_server,
        kwargs={
            "port": private_config.my_port,
            "use_tunnel": use_tunnel,
            "ngrok_domain": ngrok_domain,
            "tunnel_provider": tunnel_provider,
        },
        daemon=True,
    ).start()
    try:
        startup_grace = (
            _CLOUDFLARE_SERVER_STARTUP_GRACE_SECONDS
            if use_tunnel and tunnel_provider == "cloudflare"
            else _SERVER_STARTUP_GRACE_SECONDS
        )
        await asyncio.sleep(startup_grace)

        peer_url = private_config.opponent_url
        if private_config.initiate_step0:
            await orchestrator.negotiate_step0(peer_url)
        else:
            await orchestrator.await_passive_step0(private_config.step0_wait_seconds)

        # GUI painting is owned by LiveGuiSession on the main thread — never by
        # play_game under asyncio (blank window on Windows).
        outcome = await orchestrator.play_game(peer_url, enable_gui=False)

        score = score_outcome(outcome, config)
        await orchestrator.report_game(
            peer_url,
            outcome,
            is_counted=counted,
            opponent_id=peer_url,
            score=score,
        )

        # The real bug this closes: the server runs on a daemon thread, so the
        # instant this coroutine returns, the whole process — server, tunnel,
        # everything — exits immediately, with no equivalent to
        # `_SERVER_STARTUP_GRACE_SECONDS` on the way out. A genuinely slower
        # peer's own later Final Reveal call then hits a bare connection
        # refusal even though nothing was actually wrong — found via a real
        # cross-machine match where this side's terminal returned before the
        # peer's did. `report_game()` has already run and is unaffected by
        # this wait; it only keeps this side reachable a while longer.
        orchestrator.trace.log(
            "post_match_grace_period_started", seconds=private_config.post_match_grace_seconds
        )
        await _sleep_with_heartbeats(orchestrator, private_config.post_match_grace_seconds)
    finally:
        # Runs on *every* exit path — success, a raised Step0MismatchError
        # or other technical loss, or Ctrl+C (KeyboardInterrupt) — not
        # just the happy one a bare sequence of awaits would cover. Found
        # live: a Ctrl+C'd match left its own ngrok agent running as an
        # orphan, still claiming the domain for every later launch
        # (`ERR_NGROK_334`) — the exact "stale tunnel" class of bug this
        # session spent a long time chasing, self-inflicted from this
        # side the whole time. `run_as_server`'s own `finally:
        # stop_tunnel_if_running()` lives on the daemon thread blocking
        # inside `self.server.run(...)`, which never returns under normal
        # shutdown, so it never actually fires on its own.
        await orchestrator.close_peer_connection()
        orchestrator.stop_tunnel_if_running()
    return orchestrator
