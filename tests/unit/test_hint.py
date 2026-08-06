"""reasoning/hint.py: generate + interpret + provider cadence throttling."""

from __future__ import annotations

import random
import re
from dataclasses import replace

import pytest

from cop.domain.board import Board, Position
from cop.memory.scent import ScentField
from cop.reasoning.hint import (
    choose_provider,
    decide_intent,
    dominant_scent_direction,
    generate_hint,
    generate_scent_report,
    interpret_hint,
)
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


def test_dominant_scent_direction_on_an_asymmetric_window_finds_the_true_lean():
    own_pos = Position(3, 3)
    # All residual scent to the north-east of own_pos; nothing elsewhere.
    sampled = {
        Position(4, 2): 0.62,
        Position(5, 1): 0.20,
        own_pos: 0.90,
    }

    vertical, horizontal = dominant_scent_direction(sampled, own_pos)

    assert (vertical, horizontal) == ("north", "east")


def test_dominant_scent_direction_on_a_fresh_symmetric_window_defaults_to_north_west():
    own_pos = Position(3, 3)
    # A freshly-advanced field is radially symmetric around its own centre —
    # no real lean yet (e.g. turn 1). Every direction ties.
    sampled = {
        own_pos: 0.90,
        Position(4, 3): 0.62, Position(2, 3): 0.62,
        Position(3, 4): 0.62, Position(3, 2): 0.62,
        Position(4, 4): 0.42, Position(2, 2): 0.42,
        Position(4, 2): 0.42, Position(2, 4): 0.42,
    }

    vertical, horizontal = dominant_scent_direction(sampled, own_pos)

    assert (vertical, horizontal) == ("north", "west")


def test_generate_scent_report_respects_the_word_limit_even_when_tiny(config):
    # generate_scent_report's own template is short enough that only an
    # artificially tiny limit exercises the backstop truncation at all.
    sampled = {Position(4, 2): 0.62, Position(3, 3): 0.90}
    truncated_config = replace(config, hint_word_limit=2)

    text = generate_scent_report(sampled, Position(3, 3), truncated_config)

    assert len(text.split()) == 2


def test_generate_scent_report_never_produces_digits_that_look_like_coordinates(config):
    # "Grep the wire" (Design Question 5), extended to the scent-report
    # field (Revision 1): sweep every board position as a real trail's
    # endpoint, through a real ScentField (not a hand-built dict), across a
    # spread of prior positions so the sampled window is never trivially
    # symmetric — the same systematic-sweep discipline as
    # test_generate_hint_never_produces_digits_that_look_like_coordinates.
    board = Board(size=config.board_size)
    positions = [Position(c, r) for c in range(config.board_size) for r in range(config.board_size)]
    previous_offsets = [(-1, -1), (1, 1), (-1, 1), (1, -1), (0, 0)]

    for own_pos in positions:
        for d_col, d_row in previous_offsets:
            field = ScentField.from_config(config)
            field.advance(Position(own_pos.col + d_col, own_pos.row + d_row), board)
            field.advance(own_pos, board)
            sampled = field.sample(own_pos, board)
            text = generate_scent_report(sampled, own_pos, config)
            assert not _COORDINATE_PATTERN.search(text), f"{text!r} contains a digit"
