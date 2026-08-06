"""Can the cop actually win by entombment (rule 47)? Constructed from a
near-sealed position (2 of the thief's 4 neighbours already barrier-blocked,
cop positioned off-axis with `initial_*` seeding — `run_local_subgame`
can't reach this from `config`'s defaults in a reasonable number of turns).

Empirically verified finding, not assumed: `CopBrain`'s barrier mechanic
does engage here — round 1 places a real barrier that seals a 3rd side —
but the *final* capture in this scenario is a coordinate walk-in, not a
rule-47 zero-legal-moves capture. This is structural, not incidental: once
only one gap remains, that gap cell is always the cop's closest available
move, and the existing "never barricade your own preferred step" rule
(`cop_brain.py`) means walking always wins the tie over sealing it. A real
rule-47 *terminal* capture would need either a smarter cop heuristic (some
lookahead) or a thief mover that runs itself into a fully-sealed pocket
while the cop is off-axis — neither exists yet. Documented here as the
"strategy finding worth knowing now" this test was written to surface,
per PLAN.md's own note that heuristics are expected to compete on quality
between PRD 3 and the league.
"""

from __future__ import annotations

import random

from greedy_thief_mover import greedy_thief_move

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.domain.capture import thief_has_no_legal_move
from cop.reasoning.brain_base import PlaceBarrier
from cop.reasoning.cop_brain import CopBrain
from cop.reasoning.subgame import run_local_subgame
from cop.shared.config import GameConfig


def _stay(own_pos, board, barriers) -> str:
    return "STAY"


def test_run_local_subgame_closes_a_near_sealed_position_and_captures(config):
    board = Board(size=config.board_size)
    thief_start = Position(3, 3)
    # Thief's N and W neighbours already blocked; E and S still open.
    barriers = BarrierSet(quota=config.barrier_quota, placed={Position(3, 2), Position(2, 3)})
    # Cop diagonally SE of the thief (not adjacent) — a genuine tie between
    # two of its own neighbours in Manhattan distance to the thief, letting
    # the losing tie-break option (the thief's south neighbour) through as
    # a real, chosen barrier placement rather than always being excluded as
    # the cop's own preferred step.
    cop_start = Position(4, 4)

    events = []

    def _record(round_number, action, cop_pos, thief_pos, placed_barriers) -> None:
        events.append((action, cop_pos, thief_pos, placed_barriers))

    outcome = run_local_subgame(
        CopBrain(),
        _stay,
        board,
        config,
        on_turn=_record,
        initial_cop_pos=cop_start,
        initial_thief_pos=thief_start,
        initial_barriers=barriers,
    )

    assert outcome.value == "capture"
    assert any(isinstance(action, PlaceBarrier) for action, *_ in events), (
        "the barrier mechanic never engaged — this scenario is supposed to "
        "exercise it, not just movement"
    )

    # The documented finding: this particular capture is coordinate, not
    # rule-47. If a future, smarter heuristic starts sealing the terminal
    # gap instead of walking through it, this assertion is the one to
    # flip — that would be a genuine strategy improvement worth noting.
    final_action, final_cop_pos, final_thief_pos, final_barriers = events[-1]
    final_barrier_set = BarrierSet(quota=config.barrier_quota, placed=set(final_barriers))
    assert final_cop_pos == final_thief_pos, "expected this scenario to end in a coordinate capture"
    assert thief_has_no_legal_move(final_thief_pos, board, final_barrier_set) is False, (
        "the thief still had an unblocked neighbour at capture time — confirms this win "
        "was a walk-in, not rule 47's zero-legal-moves entombment"
    )


def test_a_full_subgame_essentially_never_exhausts_the_barrier_quota(config):
    # Related finding: §4's "quota exhausted" branch is tested in isolation
    # (test_cop_brain_barrier_policy.py), but does any *real* full game ever
    # reach it? Empirically: no. Across 50 randomized start positions
    # against the moving greedy-thief fixture, the most barriers any single
    # game ever placed was 1 — the heuristic converges to capture long
    # before quota pressure could matter. Locked in here as a documented
    # fact (fixed seed, reproducible), not a guess: if a future heuristic
    # change makes barrier placement much more aggressive, this is the
    # test that should start failing and prompt a second look.
    board = Board(size=config.board_size)
    rng = random.Random(20260806)
    max_barriers_seen = 0

    for _ in range(50):
        thief_start = (rng.randrange(config.board_size), rng.randrange(config.board_size))
        cop_start = (rng.randrange(config.board_size), rng.randrange(config.board_size))
        if thief_start == cop_start:
            continue
        trial_config = GameConfig(**{**config.__dict__, "thief_start": thief_start, "cop_start": cop_start})

        def _track(round_number, action, cop_pos, thief_pos, barriers) -> None:
            nonlocal max_barriers_seen
            max_barriers_seen = max(max_barriers_seen, len(barriers))

        run_local_subgame(CopBrain(), greedy_thief_move, board, trial_config, on_turn=_track)

    assert max_barriers_seen < config.barrier_quota, (
        f"expected quota exhaustion to stay untested end-to-end (max seen: "
        f"{max_barriers_seen}/{config.barrier_quota}) — if this now fails, the heuristic "
        f"changed enough that quota exhaustion needs a real end-to-end test, not just §4's "
        f"isolated one"
    )
