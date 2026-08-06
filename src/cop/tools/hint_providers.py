"""The `[trash_talk] provider` abstraction (Table 21) — PRD 4 Design Question 6.

Only `template` (default, zero tokens) and `ollama` (zero API tokens) are
implemented. `claude_api`/`claude_cli` are interface-only: Table 19's
token-bucket rate limiter doesn't exist until PRD 7's `policy/gatekeeper.py`,
and wiring a live, unrate-limited paid API call two layers before its own
safety net exists is exactly the kind of scaffolding this project has
already found dangerous to leave lying around once (rule 27's PRD 2
carve-out). They raise `NotImplementedError` pointing back here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from ..domain.board import Position

_QUADRANT_TEMPLATE = "Near the {vertical} {horizontal} side{landmark}."


def _quadrant(pos: Position, board_size: int) -> tuple[str, str]:
    half = board_size / 2
    vertical = "north" if pos.row < half else "south"
    horizontal = "west" if pos.col < half else "east"
    return vertical, horizontal


def _opposite(vertical: str, horizontal: str) -> tuple[str, str]:
    flipped_vertical = "south" if vertical == "north" else "north"
    flipped_horizontal = "east" if horizontal == "west" else "west"
    return flipped_vertical, flipped_horizontal


class HintProvider(ABC):
    @abstractmethod
    def generate(self, true_pos: Position, intent: bool, arena: str, word_limit: int, board_size: int) -> str:
        """Produce a hint about `true_pos` — truthful if `intent`, misleading
        otherwise. Must never exceed `word_limit` words."""


class TemplateHintProvider(HintProvider):
    """In-process, pre-written sentences — zero tokens (Table 21's default)."""

    def generate(self, true_pos: Position, intent: bool, arena: str, word_limit: int, board_size: int) -> str:
        vertical, horizontal = _quadrant(true_pos, board_size)
        if not intent:
            vertical, horizontal = _opposite(vertical, horizontal)
        landmark = f" of {arena}" if arena else ""
        text = _QUADRANT_TEMPLATE.format(vertical=vertical, horizontal=horizontal, landmark=landmark)
        words = text.split()
        if len(words) > word_limit:
            text = " ".join(words[:word_limit])
        return text


class OllamaHintProvider(HintProvider):
    """A plain HTTP call to a local Ollama instance — zero API tokens (Table 21).

    The system prompt states the word limit as an instruction to the model
    (Table 14 #2: "applies to template mode and to the LLM (stated in its
    system prompt)") — `reasoning/hint.py`'s own backstop truncation still
    applies on top; never trust one enforcement layer for a fatal rule.
    """

    def __init__(
        self, model: str = "llama3", base_url: str = "http://localhost:11434", timeout: float = 5.0
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.timeout = timeout

    def system_prompt(self, word_limit: int) -> str:
        return (
            f"You write a short, vague hint about a position on a grid game board. "
            f"Use at most {word_limit} words. Never include digits or coordinates."
        )

    def generate(self, true_pos: Position, intent: bool, arena: str, word_limit: int, board_size: int) -> str:
        vertical, horizontal = _quadrant(true_pos, board_size)
        if not intent:
            vertical, horizontal = _opposite(vertical, horizontal)
        prompt = f"The position is in the {vertical} {horizontal} area."
        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "system": self.system_prompt(word_limit),
                    "prompt": prompt,
                    "stream": False,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"could not reach Ollama at {self.base_url}: {exc}") from exc
        return response.json()["response"].strip()


class ClaudeApiHintProvider(HintProvider):
    def generate(self, true_pos: Position, intent: bool, arena: str, word_limit: int, board_size: int) -> str:
        raise NotImplementedError(
            "claude_api is interface-only until PRD 7's policy/gatekeeper.py exists to "
            "rate-limit it (Table 19, rule 28) — see PRD-4-language-and-scent.md Design Question 6."
        )


class ClaudeCliHintProvider(HintProvider):
    def generate(self, true_pos: Position, intent: bool, arena: str, word_limit: int, board_size: int) -> str:
        raise NotImplementedError(
            "claude_cli is interface-only until PRD 7's policy/gatekeeper.py exists to "
            "rate-limit it (Table 19, rule 28) — see PRD-4-language-and-scent.md Design Question 6."
        )


_PROVIDERS: dict[str, type[HintProvider]] = {
    "template": TemplateHintProvider,
    "ollama": OllamaHintProvider,
    "claude_api": ClaudeApiHintProvider,
    "claude_cli": ClaudeCliHintProvider,
}


def build_provider(name: str) -> HintProvider:
    """`[trash_talk] provider`'s factory — raises on an unrecognized name
    rather than silently falling back to `template`."""
    try:
        return _PROVIDERS[name]()
    except KeyError:
        raise ValueError(f"unrecognized hint provider: {name!r}") from None
