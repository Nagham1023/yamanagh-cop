"""Canonical `State` serialization for PRD 6's eventual commit hash — see
`PRD-6-prep-commit-payload-spec.md` for the frozen field list and why it's
this narrow. Built now, not deferred to PRD 6, so the spec is enforced in
code rather than staying a document nobody re-reads.
"""

from __future__ import annotations

from ..reasoning.state import GameState
from .canonical_json import canonical_json_bytes


def _reject_floats(value: object, path: str = "$") -> None:
    """Recursively walk a payload and raise on any float — an active,
    code-enforced version of "if a float has to be in there, fix the
    precision as a string at the boundary" (spec doc's "why"). A bool is
    not a float (`isinstance(True, float)` is `False`) and passes through
    untouched; only genuine floats trip this."""
    if isinstance(value, float):
        raise TypeError(
            f"commit payload contains a float at {path} ({value!r}) — floats are a latent "
            "hash mismatch across peers/runs; fix the precision as a string at the boundary "
            "before it reaches this function, per PRD-6-prep-commit-payload-spec.md"
        )
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_floats(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_floats(item, f"{path}[{index}]")


def canonical_state_bytes(game_state: GameState) -> bytes:
    """The `State` component of PRD 6's eventual `SHA256(State || Move ||
    Intent || Nonce)` — exactly the three fields
    `PRD-6-prep-commit-payload-spec.md` freezes (`own_pos`, `steps_taken`,
    a sorted `barriers_placed`), never `target_pos` (belief, not truth)
    and never scent/belief values (inference apparatus, not a fact about
    this agent's own state, and the actual float trap this function exists
    to close off).

    Sorts `barriers_placed` explicitly by `(col, row)` — `sort_keys=True`
    only orders dict keys, not the contents of a list, and a `set`'s
    iteration order is not something to depend on even where (as
    investigated in the spec doc) it happens to be stable today.
    """
    payload = {
        "own_pos": [game_state.own_pos.col, game_state.own_pos.row],
        "steps_taken": game_state.steps_taken,
        "barriers_placed": sorted(
            ([pos.col, pos.row] for pos in game_state.barriers.placed),
            key=lambda pair: (pair[0], pair[1]),
        ),
    }
    _reject_floats(payload)
    return canonical_json_bytes(payload)
