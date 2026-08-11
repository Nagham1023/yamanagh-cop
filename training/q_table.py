"""QTable: mutable, training-side Q-value store (PRD 11).

Deliberately a separate class from `src/cop/reasoning/rl_checkpoint.py`'s
read-only `RLQTable` — training needs updates, inference only ever needs a
ranked read. Conflating them would mean the production module either grows
mutation methods it never uses, or `training/` gets imported into
`src/cop/` to share one class — exactly the boundary
`test_training_boundary.py` exists to keep closed. `as_dict()` is the only
handoff point, consumed by `checkpoint_io.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cop.reasoning.rl_state_encoding import State

_ACTIONS = ("N", "E", "S", "W", "STAY")


@dataclass
class QTable:
    _values: dict[State, dict[str, float]] = field(default_factory=dict)

    def value(self, state: State, action: str) -> float:
        return self._values.get(state, {}).get(action, 0.0)

    def update(self, state: State, action: str, new_value: float) -> None:
        self._values.setdefault(state, {})[action] = new_value

    def best_value(self, state: State) -> float:
        row = self._values.get(state)
        return max(row.values()) if row else 0.0

    def best_legal_action(self, state: State, legal_actions: list[str]) -> str:
        """Argmax over `legal_actions` only — used by the training loop's
        greedy branch, so exploitation never proposes an illegal action
        either, same discipline `RLCopBrain` applies at inference time."""
        row = self._values.get(state, {})
        return max(legal_actions, key=lambda a: row.get(a, 0.0))

    def as_dict(self) -> dict[State, dict[str, float]]:
        return dict(self._values)
