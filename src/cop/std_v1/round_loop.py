"""The per-sub-game turn loop for std_v1's Cop role (spec Sections 5, 9,
10). The Thief always sends the first turn of a sub-game (step 1, odd);
this repo answers on the even steps, declaring `capture_claim` — its own
post-move cell — unconditionally on every single reply, per Section 5's
"no gating" rule. A capture is only ever confirmed by the Thief's own next
`claim_response`, since this repo has no ground truth about the Thief's
real position; a Thief that instead survives to `max_steps` ends the
sub-game with a `win_claim` on its own final turn, which needs no reply.
"""

from __future__ import annotations

import asyncio

from ..planner.deadline import DeadlineExceededError
from .capture import was_caught
from .exchange import StdExchange
from .sealing import build_audit_record, build_turn_message, build_turn_payload, seal_turn
from .turn_handler import Std1TurnHandler
from .wire import send_turn


async def play_sub_game(
    turn_handler: Std1TurnHandler,
    connection,
    exchange: StdExchange,
    max_steps: int,
    turn_deadline_sec: float,
    retry_attempts: int = 3,
    retry_delay_seconds: float = 1.0,
) -> tuple[str, list[dict], dict[int, str], dict[int, str]]:
    """Runs one full sub-game as the Cop. Returns `(end_reason, records,
    peer_commits, my_commits)` — `end_reason` is `"capture"`, `"survival"`,
    or `"timeout"`; `records` are this repo's own sealed turns, ready for
    the audit exchange; `peer_commits` are the Thief's own live commits,
    keyed by step, for verifying its later-revealed records against;
    `my_commits` are this side's own live-sent commits, keyed by step —
    rule 20's replay log needs both halves to be independently checkable
    without a live process. `retry_attempts`/`retry_delay_seconds` bound
    `send_turn`'s own connect-only retry, sourced from `PrivateConfig` at
    the real call site (I6)."""
    records: list[dict] = []
    peer_commits: dict[int, str] = {}
    my_commits: dict[int, str] = {}

    try:
        thief_turn = await asyncio.to_thread(exchange.wait_for_turn, 1, turn_deadline_sec)
    except DeadlineExceededError:
        return "timeout", records, peer_commits, my_commits
    peer_commits[1] = thief_turn["commit"]
    if thief_turn.get("win_claim"):
        return "survival", records, peer_commits, my_commits

    step = 2
    while step <= max_steps:
        decision = turn_handler.play_turn(thief_turn.get("smell_grid") or {}, thief_turn.get("hint") or "")
        payload = build_turn_payload(
            step=step, sender="police", move=decision["move"], hint=decision["hint"],
            smell_grid=decision["smell_grid"], barrier_placed=decision["barrier_placed"],
            capture_claim=decision["capture_claim"],
        )
        sealed = seal_turn(payload)
        records.append(build_audit_record(payload, sealed["nonce"]))
        my_commits[step] = sealed["commit"]
        await send_turn(connection, build_turn_message(payload, sealed["commit"]), retry_attempts, retry_delay_seconds)

        try:
            thief_turn = await asyncio.to_thread(
                exchange.wait_for_turn, step + 1, turn_deadline_sec
            )
        except DeadlineExceededError:
            return "timeout", records, peer_commits, my_commits
        peer_commits[step + 1] = thief_turn["commit"]

        if was_caught(thief_turn.get("claim_response")):
            return "capture", records, peer_commits, my_commits
        if thief_turn.get("win_claim"):
            return "survival", records, peer_commits, my_commits
        step += 2

    return "survival", records, peer_commits, my_commits
