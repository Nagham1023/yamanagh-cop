"""tools/hint_providers.py: the [trash_talk] provider abstraction."""

from __future__ import annotations

import itertools

import httpx
import pytest

from cop.domain.board import Position
from cop.tools.hint_providers import (
    ClaudeApiHintProvider,
    ClaudeCliHintProvider,
    OllamaHintProvider,
    TemplateHintProvider,
    build_provider,
)


def _ollama_reachable() -> bool:
    try:
        httpx.get("http://localhost:11434/api/tags", timeout=1.0)
        return True
    except httpx.HTTPError:
        return False

_BOARD_SIZE = 7
_WORD_LIMIT = 15
_ARENA = "New York"


def test_template_provider_never_exceeds_the_word_limit():
    provider = TemplateHintProvider()
    positions = [Position(c, r) for c in range(_BOARD_SIZE) for r in range(_BOARD_SIZE)]

    for pos, intent, arena in itertools.product(positions, [True, False], [_ARENA, ""]):
        text = provider.generate(pos, intent, arena, _WORD_LIMIT, _BOARD_SIZE)
        assert len(text.split()) <= _WORD_LIMIT


def test_template_provider_output_differs_between_true_and_false_intent():
    provider = TemplateHintProvider()
    true_pos = Position(0, 0)  # unambiguously north-west

    truthful = provider.generate(true_pos, True, _ARENA, _WORD_LIMIT, _BOARD_SIZE)
    lying = provider.generate(true_pos, False, _ARENA, _WORD_LIMIT, _BOARD_SIZE)

    assert truthful != lying
    assert "north" in truthful and "west" in truthful
    assert "south" in lying and "east" in lying


def test_template_provider_respects_the_empty_arena_carve_out():
    provider = TemplateHintProvider()
    text = provider.generate(Position(0, 0), True, "", _WORD_LIMIT, _BOARD_SIZE)
    assert "New York" not in text
    assert len(text.split()) <= _WORD_LIMIT


def test_template_provider_truncates_its_own_output_when_a_tight_limit_is_configured():
    # A tiny word_limit forces the template's own sentence over the limit —
    # proves the provider's own backstop truncation actually fires, not
    # just that a real 15-word limit never happens to trigger it.
    provider = TemplateHintProvider()
    text = provider.generate(Position(0, 0), True, _ARENA, 2, _BOARD_SIZE)
    assert len(text.split()) == 2


def test_ollama_provider_system_prompt_states_the_word_limit():
    provider = OllamaHintProvider()
    assert str(_WORD_LIMIT) in provider.system_prompt(_WORD_LIMIT)


def test_ollama_provider_flips_quadrant_when_intent_is_false(monkeypatch):
    # No live Ollama needed for this one: it's proving the *prompt
    # construction* branches on Intent, not that a real model responds
    # sensibly — same split as the local/wire distinction elsewhere in
    # this layer (Design Question 4).
    captured = {}

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": "a hint"}

    def _fake_post(url, json, timeout):
        captured["prompt"] = json["prompt"]
        return _FakeResponse()

    monkeypatch.setattr("cop.tools.hint_providers.httpx.post", _fake_post)
    provider = OllamaHintProvider()

    provider.generate(Position(0, 0), False, _ARENA, _WORD_LIMIT, _BOARD_SIZE)

    assert "south" in captured["prompt"] and "east" in captured["prompt"]


def test_ollama_provider_raises_a_clear_error_when_unreachable(monkeypatch):
    def _fake_post(url, json, timeout):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("cop.tools.hint_providers.httpx.post", _fake_post)
    provider = OllamaHintProvider()

    with pytest.raises(RuntimeError, match="could not reach Ollama"):
        provider.generate(Position(0, 0), True, _ARENA, _WORD_LIMIT, _BOARD_SIZE)


def test_claude_api_provider_is_not_implemented():
    with pytest.raises(NotImplementedError):
        ClaudeApiHintProvider().generate(Position(0, 0), True, _ARENA, _WORD_LIMIT, _BOARD_SIZE)


def test_claude_cli_provider_is_not_implemented():
    with pytest.raises(NotImplementedError):
        ClaudeCliHintProvider().generate(Position(0, 0), True, _ARENA, _WORD_LIMIT, _BOARD_SIZE)


def test_build_provider_returns_the_right_type():
    assert isinstance(build_provider("template"), TemplateHintProvider)
    assert isinstance(build_provider("ollama"), OllamaHintProvider)
    assert isinstance(build_provider("claude_api"), ClaudeApiHintProvider)
    assert isinstance(build_provider("claude_cli"), ClaudeCliHintProvider)


def test_build_provider_rejects_an_unrecognized_name():
    with pytest.raises(ValueError, match="unrecognized"):
        build_provider("carrier_pigeon")


@pytest.mark.skipif(not _ollama_reachable(), reason="no local Ollama instance reachable")
def test_ollama_provider_generates_a_hint_against_a_real_local_instance():
    # Not run in an environment without Ollama installed — exercised
    # manually there instead, per TODO4 §4. This environment happens to
    # have phi3:mini pulled.
    provider = OllamaHintProvider(model="phi3:mini", timeout=60.0)
    text = provider.generate(Position(0, 0), True, _ARENA, _WORD_LIMIT, _BOARD_SIZE)
    assert isinstance(text, str)
    assert len(text) > 0
