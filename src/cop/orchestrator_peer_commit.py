"""Peer commit reception — split out of `orchestrator_peer_audit.py` once
that file re-hit the 150-line cap adding the Final-Reveal race fix
(`_await_peer_final_reveal`). Cohesive on its own: receiving the peer's
`Hcommit` and logging its declared timing are a self-contained concern,
separate from the Final-Reveal exchange and the audit that follows it.
"""

from __future__ import annotations

import time


class PeerCommitMixin:
    def _on_commit_received(
        self, h_commit: str, sent_at: float | None = None, deadline_at: float | None = None
    ) -> None:
        """Server-role counterpart to `commit_and_reveal_to_peer`'s outgoing
        commit — persists the peer's own `Hcommit` into `self.peer_trace`,
        the piece PRD 6 left unwired (`on_commit` was always `None`).

        PRD 15 (ch. 8.4): `sent_at`/`deadline_at` are the peer's own
        declared request timing — logged for observability only; rule 9
        means a peer-declared deadline is never trusted to affect this
        side's own `await_with_deadline` bound. Both `None` for a peer
        whose own client predates this addition (`receive_commit`'s tool
        signature makes them optional for exactly this reason) — logged as
        `null`, not faked."""
        self.peer_trace.record_commit(h_commit)
        self.trace.log(
            "peer_commit_received", h_commit=h_commit, peer_sent_at=sent_at, peer_deadline_at=deadline_at
        )
        self._log_if_peer_deadline_already_expired(deadline_at)

    def _log_if_peer_deadline_already_expired(self, deadline_at: float | None) -> None:
        """Shared by `_on_commit_received`/`orchestrator_reveal_received.py`'s
        own `_on_reveal_received` (same mixin composition, same `self.trace`).
        Informational only — a stale `deadline_at` suggests clock skew or a
        slow/lying peer, never something this side acts on (rule 9).
        `None` (an older peer client) means nothing to compare — skipped,
        not treated as automatically expired."""
        if deadline_at is not None and time.time() > deadline_at:
            self.trace.log("peer_declared_deadline_already_expired", deadline_at=deadline_at)
