"""Persistent-connection lifecycle — split out of `orchestrator_peer.py`,
which grew past the 150-line house cap once this landed. A mixin, not a
standalone class: reaches into `self._peer_connection` (set up by
`Orchestrator.__init__`).

One `PeerConnection` per match, lazily created and reused by every
outbound call site — replaces the old "fresh `fastmcp.Client` per call"
pattern (found live: ~19+ separate connections through one free-tier
ngrok tunnel by round 6 alone, `tools/peer_connection.py`'s own docstring
has the full story).
"""

from __future__ import annotations

from .tools.peer_connection import PeerConnection


class PeerConnectionMixin:
    def _get_peer_connection(self, peer_url: str) -> PeerConnection:
        """There is only ever one peer per match, so a single cached slot
        (re-created only if the URL genuinely changes, which never
        happens mid-match) is enough — no pooling needed. No `timeout=`
        passed through (`PeerConnection`'s own docstring has the full
        reasoning) — `await_with_deadline` at every call site already
        bounds this fully."""
        if self._peer_connection is None or self._peer_connection.url != peer_url:
            self._peer_connection = PeerConnection(peer_url)
        return self._peer_connection

    async def close_peer_connection(self) -> None:
        """Explicit, idempotent teardown — called once from
        `cli_peer_match_body.py::run_match_body` right after `report_game()`
        returns, since no further outbound calls happen after that point."""
        if self._peer_connection is not None:
            await self._peer_connection.close()
            self._peer_connection = None
