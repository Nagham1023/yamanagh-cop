"""`_on_reveal_received` — server-side counterpart to `orchestrator_turn.py`'s
outgoing `take_turn`, split into its own mixin once that file re-hit the
150-line cap adding belief/scent observability logging (found needed while
diagnosing why a real cop never closed distance on a real thief across
several live matches — the missing visibility into where belief actually
was each turn was itself the blocker to finishing that diagnosis).
"""

from __future__ import annotations

from .reasoning.hint import interpret_hint


class RevealReceivedMixin:
    def _on_reveal_received(
        self, move: dict, hint_text: str, sent_at: float | None = None, deadline_at: float | None = None
    ) -> None:
        """Interpret the peer's tactical hint (possibly a lie), folding it
        into the belief map. Injected into `build_server` as `on_reveal`
        rather than importing `reasoning.hint`/`memory.belief` there —
        `tools/` stays a thin transport layer (rule 3/I2).

        `move` is an unverified claim until Final Reveal (PRD 6 DQ2) — not
        cryptographically checkable yet, since the nonce needed to recompute
        the peer's `Hcommit` doesn't exist until then; it's persisted into
        `self.peer_trace` (closing PRD 6's own "Known gap") for
        `run_peer_audit`'s later use, but never fed into belief here — only
        `hint_text` does that, and only after passing `hint_word_limit`
        (I9 — everything a peer sends is untrusted).

        `interpret_hint` returning `None` (no direction word at all) means
        skip the belief update entirely — a real, previously-missing case;
        see `hint.py::interpret_hint`'s own docstring for the live bug this
        closed (it used to default to a confident but fabricated NW pull on
        every direction-less hint, which is worse than no update at all).

        Also mirrors `hint_text` into `self._last_hint_received` for the
        live GUI (PRD 7 round-2), and logs the peer's declared `sent_at`/
        `deadline_at` (PRD 15, optional, `None` for an older client) —
        observational only, never trusted (rule 9; see
        `_log_if_peer_deadline_already_expired`, `orchestrator_peer_audit.py`)."""
        self._last_hint_received = hint_text
        self.peer_trace.record_reveal(move, hint_text)
        if len(hint_text.split()) <= self.config.hint_word_limit:
            focal_point = interpret_hint(hint_text, self.board)
            if focal_point is not None:
                self.belief_map.update_from_hint(focal_point, self.board)
        self.trace.log(
            "hint_received", text=hint_text, peer_sent_at=sent_at, peer_deadline_at=deadline_at
        )
        self._log_if_peer_deadline_already_expired(deadline_at)
