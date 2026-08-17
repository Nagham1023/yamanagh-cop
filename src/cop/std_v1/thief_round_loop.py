"""Per-sub-game turn loop for std_v1's Thief role (spec Sections 5, 9,
10) -- used only on the alternated sub-games (Section 6) when this repo
plays the opposite of its natural Police role. Movement comes from
thief_brain.choose_thief_move (a minimal greedy evasion, not a real
strategy investment); wire protocol and sealing mirror round_loop.py's
own Police-role loop, with sender/turn-order swapped: this side sends
first (Section 10, "the Thief sends the first turn of every sub-game")
and evaluates the peer's `capture_claim`/`barrier_placed` against its
own true position (Section 5) instead of declaring a claim.
"""

from __future__ import annotations

import asyncio

from ..domain.board import Position
from ..domain.capture import is_barrier_capture, is_coordinate_capture, thief_has_no_legal_move
from ..planner.deadline import DeadlineExceededError
from ..reasoning.brain_base import Move
from .sealing import build_audit_record, build_turn_message, build_turn_payload, seal_turn
from .thief_brain import believed_cop_cell, choose_thief_move
from .wire import send_turn


def _parse_smell_grid(wire_grid: dict) -> dict[Position, float]:
    """Wire keys are `"row,col"` (the paired Thief repo's own `Cell`
    convention) -- the opposite axis order from this repo's
    `Position(col, row)`, so every key is explicitly swapped."""
    parsed: dict[Position, float] = {}
    for key, value in wire_grid.items():
        row_str, col_str = key.split(",")
        parsed[Position(int(col_str), int(row_str))] = float(value)
    return parsed


def _serialize_smell_grid(field: dict[Position, float]) -> dict[str, float]:
    return {f"{pos.row},{pos.col}": value for pos, value in field.items() if value > 0.0}


def _wire_to_position(coord: list[int]) -> Position:
    """`[row, col]` on the wire -> this repo's own `Position(col, row)`."""
    row, col = coord
    return Position(col, row)


def _evaluate_capture(state, board, capture_claim: list[int], barrier_placed: list[int] | None) -> bool:
    """Spec Section 5's three terminal conditions (A/B/C). `barrier_placed`,
    when present, is recorded into `state.barriers` before condition C is
    checked -- "after the declared barrier is applied"."""
    claim_pos = _wire_to_position(capture_claim)
    if is_coordinate_capture(claim_pos, state.own_pos):
        return True
    if barrier_placed is not None:
        barrier_pos = _wire_to_position(barrier_placed)
        state.barriers.placed.add(barrier_pos)
        if is_barrier_capture(barrier_pos, state.own_pos):
            return True
        if thief_has_no_legal_move(state.own_pos, board, state.barriers):
            return True
    return False


async def play_sub_game(
    board,
    state,
    scent_field,
    connection,
    exchange,
    max_steps: int,
    turn_deadline_sec: float,
    retry_attempts: int = 3,
    retry_delay_seconds: float = 1.0,
) -> tuple[str, list[dict], dict[int, str], dict[int, str]]:
    """Runs one full sub-game as the Thief. Returns `(end_reason, records,
    peer_commits, my_commits)`, the same shape as round_loop.py's own
    Police-role `play_sub_game` — `my_commits` are this side's own
    live-sent commits, keyed by step, which rule 20's replay log needs
    alongside `peer_commits` to be independently checkable. `retry_attempts`/
    `retry_delay_seconds` bound each `send_turn`'s own connect-only retry,
    sourced from `PrivateConfig` at the real call site (I6)."""
    records: list[dict] = []
    peer_commits: dict[int, str] = {}
    my_commits: dict[int, str] = {}
    last_cop_scent: dict = {}
    pending_claim_response: dict | None = None

    step = 1
    while step <= max_steps:
        threat = believed_cop_cell(_parse_smell_grid(last_cop_scent), fallback=state.target_pos)
        direction = choose_thief_move(board, state.own_pos, state.barriers, threat)
        state.apply(Move(direction=direction), board)
        scent_field.advance(state.own_pos, board)

        win_claim = {"type": "survival"} if step == max_steps else None
        payload = build_turn_payload(
            step=step, sender="thief", move=direction, hint="",
            smell_grid=_serialize_smell_grid(scent_field.full_field()),
            claim_response=pending_claim_response, win_claim=win_claim,
        )
        sealed = seal_turn(payload)
        records.append(build_audit_record(payload, sealed["nonce"]))
        my_commits[step] = sealed["commit"]
        await send_turn(connection, build_turn_message(payload, sealed["commit"]), retry_attempts, retry_delay_seconds)
        pending_claim_response = None

        if win_claim is not None:
            return "survival", records, peer_commits, my_commits

        try:
            cop_message = await asyncio.to_thread(exchange.wait_for_turn, step + 1, turn_deadline_sec)
        except DeadlineExceededError:
            return "timeout", records, peer_commits, my_commits
        peer_commits[cop_message["step"]] = cop_message["commit"]

        caught = _evaluate_capture(
            state, board, cop_message["capture_claim"], cop_message.get("barrier_placed")
        )
        claim_response = {"claim": cop_message["capture_claim"], "caught": caught}

        if caught:
            # Section 5: a caught Thief still owes one final sealed
            # no-move STAY carrying the truthful answer.
            final_step = step + 1
            final_payload = build_turn_payload(
                step=final_step, sender="thief", move="STAY", hint="",
                smell_grid=_serialize_smell_grid(scent_field.full_field()), claim_response=claim_response,
            )
            final_sealed = seal_turn(final_payload)
            records.append(build_audit_record(final_payload, final_sealed["nonce"]))
            my_commits[final_step] = final_sealed["commit"]
            await send_turn(
                connection, build_turn_message(final_payload, final_sealed["commit"]),
                retry_attempts, retry_delay_seconds,
            )
            return "capture", records, peer_commits, my_commits

        pending_claim_response = claim_response
        last_cop_scent = cop_message.get("smell_grid") or {}
        step += 2

    return "survival", records, peer_commits, my_commits
