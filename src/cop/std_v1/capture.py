"""Capture declaration for the std_v1 protocol's Cop role (spec Section
5). This repo only ever *sends* a `capture_claim`, unconditionally, on
every single Cop turn — including a barrier-placement turn, where the
claimed cell is the cop's own (unchanged) position, since it forwent
movement — never gated on belief matching the way this repo's native
protocol's own `reasoning/state.py::claims_capture` is (rule 21/22's own
"declare only the truth" is still honored: the *position* claimed is
always this repo's real, current position, never a guess).

Wire coordinates are `[row, col]` (spec convention, matching the paired
Thief repo's own `thief_peer.domain.board.Cell` tuples) — the opposite
order from this repo's own `Position(col, row)`, so every claim built or
parsed here does an explicit swap; getting this backwards would silently
send a claim at the transposed cell.
"""

from __future__ import annotations

from ..domain.board import Position


def build_capture_claim(cop_pos: Position) -> list[int]:
    """The wire's `capture_claim = [row, col]` for this repo's own current
    position, sent unconditionally on every Cop turn."""
    return [cop_pos.row, cop_pos.col]


def build_barrier_declaration(barrier_target: Position) -> list[int]:
    """The wire's `barrier_placed = [row, col]`, present only on a turn
    where this repo actually placed a barrier this turn."""
    return [barrier_target.row, barrier_target.col]


def was_caught(claim_response: dict | None) -> bool:
    """True only once the Thief's own `claim_response = {"claim": [...],
    "caught": true}` has arrived — this repo has no other way to learn a
    capture actually happened, since it never sees the Thief's true
    position itself."""
    return bool(claim_response) and claim_response.get("caught") is True
