"""The PRD 4 milestone, local: a known-false hint measurably shifts
BeliefMap's probability mass toward the *wrong* region relative to the
cop's actual position, while ScentField's decay proceeds correctly and
independently underneath it. No Orchestrator, no network, no subprocess —
pure function calls over memory/ + reasoning/hint.py, matching PRD 3's
reasoning/subgame.py precedent (Design Question 4).

PRD 4 "Revision 3" (todoFullFix.md §C8): the corroboration tests below use
`update_from_scent_map` with real `ScentField.full_field()` data — the
language-based round-trip (field -> sentence -> re-parsed Position) this
file used to test is gone; there's no decode step left to have a category
error in.
"""

from __future__ import annotations

import random

from cop.domain.board import Board, Position
from cop.memory.belief import BeliefMap
from cop.memory.scent import ScentField
from cop.reasoning.hint import decide_intent, generate_hint, interpret_hint
from cop.tools.hint_providers import TemplateHintProvider


def test_a_known_false_hint_measurably_shifts_belief_toward_the_wrong_region(config):
    board = Board(size=config.board_size)
    true_pos = Position(0, 0)  # the cop's real position: unambiguously north-west
    belief = BeliefMap.uniform(board)
    provider = TemplateHintProvider()
    rng = random.Random(20260806)

    # Force the lie deterministically — the milestone needs Intent=False on
    # demand, not "sometimes."
    intent = decide_intent(lie_probability=1.0, rng=rng)
    assert intent is False

    hint_text = generate_hint(true_pos, provider, config, intent)
    focal_point = interpret_hint(hint_text, board)
    belief.update_from_hint(focal_point, board)

    # A truthful hint about (0, 0) would point north-west; the lie points
    # south-east instead — belief should shift toward the region *opposite*
    # the cop's real position, not toward it.
    true_quadrant_probability = belief.probability(Position(0, 0))
    lied_quadrant_probability = belief.probability(focal_point)
    assert lied_quadrant_probability > true_quadrant_probability
    assert focal_point.row > board.size / 2
    assert focal_point.col > board.size / 2


def test_scent_decay_proceeds_correctly_and_independently_of_what_the_hint_said(config):
    # Same scenario as above, but proving the *other* half of the
    # milestone's "independent" claim: scent's own decay math doesn't care
    # what the belief map did, or what the hint said.
    board = Board(size=config.board_size)
    true_pos = Position(0, 0)
    belief = BeliefMap.uniform(board)
    scent = ScentField.from_config(config)
    provider = TemplateHintProvider()
    rng = random.Random(20260806)

    scent.advance(true_pos, board)
    intent = decide_intent(lie_probability=1.0, rng=rng)
    hint_text = generate_hint(true_pos, provider, config, intent)
    focal_point = interpret_hint(hint_text, board)
    belief.update_from_hint(focal_point, board)  # deception applied to belief

    # Advancing elsewhere each subsequent turn (the agent moved away) means
    # true_pos's residual only decays — no fresh deposit lands there again,
    # matching test_scent.py's own "cell outside this turn's kernel only
    # decays" case.
    far_pos = Position(board.size - 1, board.size - 1)
    levels = [scent.sample(true_pos, board)[true_pos]]
    for _ in range(5):
        scent.advance(far_pos, board)
        levels.append(scent.sample(true_pos, board)[true_pos])

    for before, after in zip(levels[:-1], levels[1:], strict=True):
        expected = before * (1 - config.scent_decay_rate)
        assert abs(after - expected) < 1e-9

    # The belief map's own deception-induced shift never touches scent.
    assert scent.sample(true_pos, board)[true_pos] == levels[-1]


def test_a_truthful_scent_map_corroborates_against_a_lying_hint_and_wins(config):
    # The Revision 1/3 milestone: PLAN.md's "single largest differentiator
    # in the grade" — the corroboration mechanic actually working, not just
    # "a lie shifts belief wrong in isolation" (proven above). True position
    # chosen clear of any board edge so the fresh kernel deposited at
    # true_pos is itself perfectly symmetric (no clipping bias) — every bit
    # of directional lean in the field comes from the earlier, still-
    # decaying residue at `previous_pos`, not from board-edge clipping.
    board = Board(size=config.board_size)
    true_pos = Position(2, 2)  # north-west quadrant, 2 cells clear of every edge
    previous_pos = Position(1, 1)  # further north-west still — a real trail
    belief = BeliefMap.uniform(board)
    scent = ScentField.from_config(config)
    provider = TemplateHintProvider()
    rng = random.Random(20260806)

    intent = decide_intent(lie_probability=1.0, rng=rng)
    assert intent is False
    hint_text = generate_hint(true_pos, provider, config, intent)
    lie_focal_point = interpret_hint(hint_text, board)

    scent.advance(previous_pos, board)
    scent.advance(true_pos, board)

    belief.update_from_hint(lie_focal_point, board)
    belief.update_from_scent_map(scent.full_field(), board)

    # Real per-cell resolution (not the old language decoder's quadrant
    # granularity) — the corroborated argmax lands exactly on the true
    # cell, not merely in a region that outweighs the lie's.
    assert belief.most_likely_cell() == true_pos
    assert belief.probability(true_pos) > belief.probability(lie_focal_point)


def test_scent_map_corroboration_lands_on_the_true_cell_regardless_of_trail_direction(config):
    # The counterexample that drove PRD 4 Revision 2 (a relative-vs-absolute
    # category error in the old language-based decoder): own_pos in one
    # corner, the immediately preceding position in the diagonally opposite
    # corner — an entirely ordinary "just arrived" trajectory. The numeric
    # channel has no language decode step left to get this backwards in —
    # belief must land exactly on the true cell regardless of which
    # direction the trail came from.
    board = Board(size=config.board_size)
    own_pos = Position(5, 1)  # north-east, clear of every edge
    scent = ScentField.from_config(config)
    scent.advance(Position(2, 4), board)  # south-west — the opposite corner
    scent.advance(own_pos, board)

    belief = BeliefMap.uniform(board)
    belief.update_from_scent_map(scent.full_field(), board)

    assert belief.most_likely_cell() == own_pos
