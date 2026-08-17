"""Curriculum sparring opponents: always legal, and stage 1 actually prefers
more open cells (the property PRD-3's own framing names)."""

from __future__ import annotations

import random

from cop.domain.barriers import BarrierSet
from cop.domain.board import Board, Position
from cop.domain.movement import apply_move
from training.opponent_policies import (
    greedy_escape_thief,
    lookahead_evader_thief,
    make_random_walk_thief,
    make_scent_backtracking_thief,
)

_BOARD = Board(size=7)


def test_random_walk_thief_always_returns_a_legal_move():
    rng = random.Random(20260812)
    mover = make_random_walk_thief(rng)
    barriers = BarrierSet(quota=14)
    for _ in range(200):
        pos = Position(rng.randrange(7), rng.randrange(7))
        direction = mover(pos, _BOARD, barriers)
        assert direction == "STAY" or apply_move(pos, direction, _BOARD) is not None


def test_random_walk_thief_is_deterministic_for_a_given_seeded_rng():
    barriers = BarrierSet(quota=14)
    first = make_random_walk_thief(random.Random(1))(Position(3, 3), _BOARD, barriers)
    second = make_random_walk_thief(random.Random(1))(Position(3, 3), _BOARD, barriers)
    assert first == second


def test_random_walk_thief_stays_when_fully_boxed_in():
    rng = random.Random(0)
    mover = make_random_walk_thief(rng)
    corner = Position(0, 0)
    barriers = BarrierSet(quota=14, placed={Position(1, 0), Position(0, 1)})
    assert mover(corner, _BOARD, barriers) == "STAY"


def test_greedy_escape_thief_always_returns_a_legal_move():
    rng = random.Random(20260812)
    barriers = BarrierSet(quota=14)
    for _ in range(200):
        pos = Position(rng.randrange(7), rng.randrange(7))
        direction = greedy_escape_thief(pos, _BOARD, barriers)
        assert direction == "STAY" or apply_move(pos, direction, _BOARD) is not None


def test_greedy_escape_thief_prefers_the_neighbour_with_more_open_escape_routes():
    # From (0,1): candidates are N=(0,0) [2 open neighbours], S=(0,2) [2, one
    # blocked], E=(1,1) [3, one blocked] — E is the unique, unambiguous best.
    barriers = BarrierSet(quota=14, placed={Position(1, 2)})
    direction = greedy_escape_thief(Position(0, 1), _BOARD, barriers)
    assert direction == "E"


def test_greedy_escape_thief_stays_when_fully_boxed_in():
    corner = Position(0, 0)
    barriers = BarrierSet(quota=14, placed={Position(1, 0), Position(0, 1)})
    assert greedy_escape_thief(corner, _BOARD, barriers) == "STAY"


def test_lookahead_evader_thief_always_returns_a_legal_move():
    rng = random.Random(20260812)
    barriers = BarrierSet(quota=14)
    for _ in range(200):
        pos = Position(rng.randrange(7), rng.randrange(7))
        direction = lookahead_evader_thief(pos, _BOARD, barriers)
        assert direction == "STAY" or apply_move(pos, direction, _BOARD) is not None


def test_lookahead_evader_thief_is_deterministic():
    barriers = BarrierSet(quota=14, placed={Position(1, 2)})
    first = lookahead_evader_thief(Position(0, 1), _BOARD, barriers)
    second = lookahead_evader_thief(Position(0, 1), _BOARD, barriers)
    assert first == second


def test_lookahead_evader_thief_stays_when_fully_boxed_in():
    corner = Position(0, 0)
    barriers = BarrierSet(quota=14, placed={Position(1, 0), Position(0, 1)})
    assert lookahead_evader_thief(corner, _BOARD, barriers) == "STAY"


def test_lookahead_evader_thief_genuinely_looks_two_ply_deep_not_just_one():
    """A real, found-not-constructed-by-hand disagreement: greedy_escape_thief
    (1-ply) and lookahead_evader_thief (2-ply) pick *different* legal
    directions from the same state — proving the deeper lookahead changes
    the actual decision, not just its tie-breaking."""
    pos = Position(2, 5)
    barriers = BarrierSet(
        quota=14,
        placed={
            Position(1, 2), Position(0, 4), Position(5, 4),
            Position(3, 3), Position(2, 6), Position(1, 0),
        },
    )
    assert greedy_escape_thief(pos, _BOARD, barriers) == "N"
    assert lookahead_evader_thief(pos, _BOARD, barriers) == "E"


def test_scent_backtracking_thief_always_returns_a_legal_move(config):
    rng = random.Random(20260812)
    mover = make_scent_backtracking_thief(config, rng)
    barriers = BarrierSet(quota=14)
    for _ in range(200):
        pos = Position(rng.randrange(7), rng.randrange(7))
        direction = mover(pos, _BOARD, barriers)
        assert direction == "STAY" or apply_move(pos, direction, _BOARD) is not None


def test_scent_backtracking_thief_is_deterministic_for_a_given_seeded_rng(config):
    barriers = BarrierSet(quota=14)
    path = [Position(3, 3), Position(3, 2), Position(3, 3)]

    def _walk(seed):
        mover = make_scent_backtracking_thief(config, random.Random(seed))
        moves = []
        for pos in path:
            moves.append(mover(pos, _BOARD, barriers))
        return moves

    assert _walk(1) == _walk(1)


def test_scent_backtracking_thief_stays_when_fully_boxed_in(config):
    rng = random.Random(0)
    mover = make_scent_backtracking_thief(config, rng)
    corner = Position(0, 0)
    barriers = BarrierSet(quota=14, placed={Position(1, 0), Position(0, 1)})
    assert mover(corner, _BOARD, barriers) == "STAY"


def test_scent_backtracking_thief_genuinely_prefers_its_own_high_scent_cell_over_a_fresh_one(config):
    # Walk the mover back and forth over (3,3) a few times so its own scent
    # field builds a clear high point there, then confirm from a branching
    # position it picks the direction back toward that high-scent cell over
    # an equally-legal, never-visited direction -- proving this is genuinely
    # different behavior from every other stage, not just a relabeled
    # random walk (every other mover is indifferent to its own history).
    rng = random.Random(20260813)
    mover = make_scent_backtracking_thief(config, rng)
    barriers = BarrierSet(quota=14)
    # hot_cell near a corner, branch_point 3 rows south along the same
    # column, both interior (all 4 directions stay legal from branch_point):
    # "N" is the only orthogonal neighbor of branch_point within Chebyshev
    # distance 2 of hot_cell, so it alone picks up a real pre-existing
    # residual from the 5 hot_cell visits; "S"/"E"/"W" are all distance 3+
    # (outside the 5x5 kernel), reading zero residual. The mover's own call
    # at branch_point deposits its own kernel there too (`_mover` advances
    # before scoring) -- a flat +0.62 to every orthogonal neighbor -- so
    # "N" ends at the Appendix E `min(source_strength, ...)` cap (0.9) while
    # "S"/"E"/"W" land at exactly 0.62, not zero, but still strictly below
    # "N": a positioning one cell closer (Chebyshev 2, not 3+) used to let
    # that same self-deposit push a "fresh" neighbor's residual over the
    # cap too, tying with "N" and turning this into an ambiguous rng.choice
    # (scent.py's own fix).
    hot_cell = Position(1, 1)
    branch_point = Position(1, 4)

    for _ in range(5):
        mover(hot_cell, _BOARD, barriers)  # repeatedly "visit" hot_cell to build up its scent

    direction = mover(branch_point, _BOARD, barriers)
    assert direction == "N"


def test_scent_backtracking_thief_needs_a_fresh_scent_field_per_episode_not_a_reused_one(config):
    # The RNG-lifetime-inverse risk this piece's own docstring warns about,
    # demonstrated concretely: reusing one mover object across two
    # "episodes" (not rebuilding it, the exact bug train_loop.py's own
    # per-episode construction avoids) lets episode 1's trail bias episode
    # 2's very first decision, even though episode 2 never actually visited
    # that cell. A freshly-built mover, by contrast, has no such bias --
    # both branches start genuinely tied (zero scent each), so across many
    # seeds it must pick each side at least once, not deterministically favor
    # the cell a *different*, no-longer-relevant mover happened to visit.
    barriers = BarrierSet(quota=14)
    # Same geometry and reasoning as the sibling test above.
    hot_cell = Position(1, 1)
    branch_point = Position(1, 4)  # "N" returns toward hot_cell; "S" is the fresh direction

    reused_mover = make_scent_backtracking_thief(config, random.Random(1))
    for _ in range(5):
        reused_mover(hot_cell, _BOARD, barriers)  # "episode 1" heavily visits hot_cell
    # "episode 2" incorrectly reuses the same object, never revisiting
    # hot_cell itself -- yet the stale trail still biases the very first
    # decision, exactly the corruption a fresh-per-episode rebuild avoids.
    assert reused_mover(branch_point, _BOARD, barriers) == "N"

    # A genuinely fresh mover, one per attempt (matching train_loop.py's own
    # correct per-episode rebuild), has no such bias -- across several
    # different seeds it must choose the fresh direction at least once.
    fresh_choices = {
        make_scent_backtracking_thief(config, random.Random(seed))(branch_point, _BOARD, barriers)
        for seed in range(10)
    }
    assert "S" in fresh_choices
