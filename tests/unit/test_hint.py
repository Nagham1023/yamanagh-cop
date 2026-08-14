"""reasoning/hint.py: generate + interpret + provider cadence throttling.

PRD 4 "Revision 3" (todoFullFix.md §C8): the scent-report tests that used
to live here (dominant_scent_direction, generate_scent_report) moved to
tests/unit/test_scent.py's full_field() tests and
tests/unit/test_scent_wire.py's serialization tests — this module now only
ever handles the natural-language tactical hint.
"""

from __future__ import annotations

import random
import re

import pytest

from cop.domain.board import Board, Position
from cop.reasoning.hint import choose_provider, decide_intent, generate_hint, interpret_hint
from cop.tools.hint_providers import HintProvider, TemplateHintProvider

_COORDINATE_PATTERN = re.compile(r"\d")


class _IgnoresWordLimitProvider(HintProvider):
    """A deliberately non-compliant provider — proves `generate_hint`'s own
    backstop truncation actually fires, not just that well-behaved providers
    happen to stay short (never trust a single enforcement layer, rule 27)."""

    def generate(self, true_pos, intent, arena, word_limit, board_size) -> str:
        return " ".join(f"word{i}" for i in range(word_limit + 5))


def test_decide_intent_forced_to_always_lie():
    rng = random.Random(1)
    assert decide_intent(lie_probability=1.0, rng=rng) is False


def test_decide_intent_forced_to_never_lie():
    rng = random.Random(1)
    assert decide_intent(lie_probability=0.0, rng=rng) is True


def test_generate_hint_with_false_intent_is_misleading_in_a_checkable_way(config):
    provider = TemplateHintProvider()
    true_pos = Position(0, 0)  # true quadrant: north-west

    text = generate_hint(true_pos, provider, config, intent=False)

    assert "south" in text and "east" in text
    assert "north" not in text and "west" not in text


def test_generate_hint_with_true_intent_matches_the_real_quadrant(config):
    provider = TemplateHintProvider()
    true_pos = Position(0, 0)

    text = generate_hint(true_pos, provider, config, intent=True)

    assert "north" in text and "west" in text


def test_generate_hint_never_produces_digits_that_look_like_coordinates(config):
    provider = TemplateHintProvider()
    positions = [Position(c, r) for c in range(config.board_size) for r in range(config.board_size)]

    for pos in positions:
        for intent in (True, False):
            text = generate_hint(pos, provider, config, intent)
            assert not _COORDINATE_PATTERN.search(text), f"{text!r} contains a digit"


def test_generate_hint_truncates_even_when_the_provider_ignores_the_word_limit(config):
    text = generate_hint(Position(0, 0), _IgnoresWordLimitProvider(), config, intent=True)
    assert len(text.split()) == config.hint_word_limit


def test_interpret_hint_on_a_north_west_hint_produces_a_north_west_focal_point():
    board = Board(size=7)
    focal_point = interpret_hint("Near the north west side of New York.", board)
    assert focal_point.row < board.size / 2
    assert focal_point.col < board.size / 2


def test_interpret_hint_on_a_south_east_hint_produces_a_south_east_focal_point():
    board = Board(size=7)
    focal_point = interpret_hint("Near the south east side of New York.", board)
    assert focal_point.row > board.size / 2
    assert focal_point.col > board.size / 2


def test_interpret_hint_returns_none_when_no_direction_word_is_present():
    # The real live bug (weighted_cop_brain.py/orchestrator_reveal_received.py
    # module docstrings have the full story): a hint with zero direction
    # words used to silently default to a confident north-west focal point
    # instead of genuinely meaning "no new information." A real opponent's
    # actual hint text, containing zero direction words.
    board = Board(size=7)
    assert interpret_hint("Ask anyone near New York -- they haven't seen me.", board) is None
    assert interpret_hint("Last seen heading toward New York.", board) is None


def test_interpret_hint_still_resolves_a_hint_that_specifies_only_one_axis():
    # Not a blanket "any missing word means None" check: a hint naming only
    # one axis is genuine partial information, not the fully-uninformative
    # case the None guard targets.
    board = Board(size=7)
    focal_point = interpret_hint("Somewhere north of here.", board)
    assert focal_point is not None
    assert focal_point.row < board.size / 2


def test_interpret_hint_shifts_a_belief_map_toward_the_hinted_region():
    from cop.memory.belief import BeliefMap

    board = Board(size=7)
    belief = BeliefMap.uniform(board)
    focal_point = interpret_hint("Near the south east side.", board)
    before = belief.probability(focal_point)

    belief.update_from_hint(focal_point, board)

    assert belief.probability(focal_point) > before


def test_choose_provider_returns_template_on_an_off_cadence_step():
    configured = object()
    template = object()

    result = choose_provider(
        step_number=2, configured_provider=configured, template_provider=template, every_n_steps=3
    )

    assert result is template


def test_choose_provider_returns_configured_on_a_cadence_step():
    configured = object()
    template = object()

    result = choose_provider(
        step_number=3, configured_provider=configured, template_provider=template, every_n_steps=3
    )

    assert result is configured


@pytest.mark.parametrize("every_n_steps", [1])
def test_choose_provider_always_returns_configured_when_every_n_steps_is_one(every_n_steps):
    configured = object()
    template = object()

    for step in range(1, 6):
        assert (
            choose_provider(step, configured, template, every_n_steps) is configured
        )
