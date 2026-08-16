"""PRD 10's passive half of the ch. 5.5 negotiation ceremony — split out of
`orchestrator_step0.py`, which would otherwise cross the 150-line house cap
once this landed alongside it. Sibling mixin, not a standalone class:
`_on_step0_received` (`Step0NegotiationMixin`) calls `_signal_step0_received`
defined here, and both reach into `self.state_machine`/`self.trace`, all of
which `Orchestrator.__init__` sets up.

`negotiate_step0` (`orchestrator_step0.py`) is the CLI's *initiating* side —
`cli_peer.py` calls it when `[network].initiate_step0 = true`. This module
is the *other* side's own wait: `await_passive_step0`, called instead when
`initiate_step0 = false`, so the passive process doesn't have to guess when
(or whether) the peer's own incoming `receive_step0` call has already
completed.

Same cross-loop signaling PRD 8's own `orchestrator_capture.py` already
established (`_capture_response_event`/`_capture_response_loop`,
`call_soon_threadsafe`) — reused deliberately, not reinvented: a passive
waiter parked in `await_passive_step0` runs on one event loop;
`_on_step0_received` fires from the server's own, genuinely separate
thread/loop (`run_as_server`). Calling `Event.set()` directly from that
thread would silently fail to wake the waiter, the exact real,
reproducible hang PRD 8's own retrospective documents finding the hard
way — not a hypothetical risk here either.

**`rule-auditor` found a second, distinct race this reuse alone didn't
close, confirmed by actually reproducing it, not just by reading the
code**: `orchestrator_capture.py`'s own pattern is safe *because* the
loop is captured immediately before the outbound send that causally
*triggers* the response — nothing can arrive first. `await_passive_step0`
has no such ordering: `_on_step0_received` is driven entirely by the
*peer's own independent timing* (in the CLI, `cli_peer.py`'s 0.5s
`run_as_server` startup grace window is more than enough), so a
negotiation can complete in full — state already `WAITING_FOR_OPPONENT`,
`_opponent_repos` already set — *before* `await_passive_step0` is ever
called. The original version unconditionally reset `self.state_machine`
and waited regardless, discarding that real result and burning the full
timeout on an `Event` nothing would ever set again. Fixed with
`self._step0_completed` (new `Orchestrator.__init__` state, set once by
`_signal_step0_received`, checked twice here — before *and* after this
function's own setup, closing the gap between the two): if Step-0 already
resolved by either check, return/raise immediately, `state_machine`
untouched — never reset an outcome that already exists.
"""

from __future__ import annotations

import asyncio

from .orchestrator_step0 import Step0MismatchError
from .planner.deadline import DeadlineExceededError
from .planner.state_machine import PeerStateMachine

# Robustness pacing cap, not a game-rule quantity (I6 doesn't apply — same
# category as cli_peer_match_body.py's own heartbeat-interval cap): an
# upper bound on how long a single chunk of the passive Step-0 wait runs
# before heartbeating the watchdog again.
_STEP0_HEARTBEAT_INTERVAL_CAP_SECONDS = 5.0


class Step0PassiveWaitMixin:
    def _signal_step0_received(self, failure: Exception | None) -> None:
        """Called by `_on_step0_received` on both its outcomes. Records
        `failure` (or `None` on success) and marks `_step0_completed` —
        the durable fact `await_passive_step0` checks even if it hasn't
        been called yet — then wakes a concurrent waiter if one already
        exists (`_step0_received_loop` still `None` is the common case:
        nothing passively waiting yet, or ever, for any non-CLI caller)."""
        self._step0_failure = failure
        self._step0_completed = True
        loop = self._step0_received_loop
        if loop is not None:
            loop.call_soon_threadsafe(self._step0_received_event.set)

    async def await_passive_step0(self, timeout_seconds: float) -> None:
        """The passive side's counterpart to `negotiate_step0`: waits for
        the peer to dial in and complete `_on_step0_received` instead of
        dialing out itself.

        Checked *twice*, not once — before touching any state, and again
        right after `_step0_received_loop` is set — because
        `_on_step0_received` can complete in full before this function is
        ever called (the module docstring's own reproduced race). Either
        check finding `_step0_completed` already `True` returns/raises
        immediately, `self.state_machine` left exactly as
        `_on_step0_received` already correctly set it — never reset to
        `NEGOTIATING` over top of a real, already-resolved outcome.

        Only once neither check finds a prior result does this actually
        become the ceremony's own first side to run: `state_machine` set
        to `NEGOTIATING` (mirroring `negotiate_step0`'s own first line),
        the loop already captured *before* this line — the same ordering
        `orchestrator_capture.py` already learned the hard way — so a call
        arriving from here on is never missed.
        """
        if self._step0_completed:
            if self._step0_failure is not None:
                raise self._step0_failure
            return

        self._step0_received_event.clear()
        self._step0_received_loop = asyncio.get_running_loop()

        if self._step0_completed:
            if self._step0_failure is not None:
                raise self._step0_failure
            return

        self.state_machine = PeerStateMachine(state="NEGOTIATING")
        self.trace.log("step0_awaiting_peer", timeout_seconds=timeout_seconds)

        try:
            await self._await_step0_event_with_heartbeats(timeout_seconds)
        except Exception as exc:
            reason = f"no peer initiated Step-0 within {timeout_seconds}s: {exc}"
            self.trace.log("step0_mismatch", reason=reason)
            self.state_machine.transition("TECHNICAL_LOSS")
            raise Step0MismatchError(reason) from exc

        if self._step0_failure is not None:
            raise self._step0_failure

    async def _await_step0_event_with_heartbeats(self, timeout_seconds: float) -> None:
        """Heartbeats between chunks of the wait instead of one bare
        `asyncio.wait_for` — the exact bug `_sleep_with_heartbeats`
        (`cli_peer_match_body.py`) already closed for the *post*-match
        grace wait, found live here too: a real match's own passive side
        self-terminated (`watchdog_controlled_shutdown`) well under a
        minute into a legitimate, up-to-`step0_wait_seconds` wait for the
        opponent to dial in — nothing about this wait ever fed the
        watchdog a heartbeat, so it looked identical to a genuinely frozen
        process despite being correctly, harmlessly idle."""
        interval = min(_STEP0_HEARTBEAT_INTERVAL_CAP_SECONDS, self.config.watchdog_threshold_seconds / 2)
        elapsed = 0.0
        while elapsed < timeout_seconds:
            chunk = min(interval, timeout_seconds - elapsed)
            try:
                await asyncio.wait_for(self._step0_received_event.wait(), timeout=chunk)
                return
            except TimeoutError:
                elapsed += chunk
                self.watchdog.heartbeat()
        raise DeadlineExceededError(f"opponent did not respond within {timeout_seconds}s")
