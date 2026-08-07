"""Wire serialization for the scent-map MCP tool (todoFullFix.md §C2, PRD 4
"Revision 3") — converts `ScentField.full_field()`'s `dict[Position, float]`
to/from the JSON-safe shape an MCP tool can actually return.

A `Position` isn't a valid JSON object key (MCP/JSON keys are strings only),
so the wire shape is a flat list of `[col, row, value]` triples rather than
a dict keyed by position: `{"cells": [[c, r, v], ...]}`. Deliberately the
*only* key in the payload — pure numeric scent data, nothing else from
`GameState` (own claimed position, barriers, ...) belongs here, the same
"grep the wire" discipline PRD 4's original coordinate-leak sweep applied
to the natural-language hint.
"""

from __future__ import annotations

from typing import Any

from ..domain.board import Position

_CellTriple = list[float]


def serialize_scent_field(scent_data: dict[Position, float]) -> dict[str, list[_CellTriple]]:
    """`ScentField.full_field()`'s output, made wire-safe."""
    return {"cells": [[pos.col, pos.row, value] for pos, value in scent_data.items()]}


def deserialize_scent_field(wire_data: dict[str, Any]) -> dict[Position, float]:
    """The inverse of `serialize_scent_field` — the receiving side's own
    reconstruction of the sender's scent field, ready for
    `memory.belief.BeliefMap.update_from_scent_map`.

    Rule 9 (CLAUDE.md) — everything a peer sends is untrusted: validates the
    shape before touching state, rather than letting a malformed payload
    (missing `"cells"`, a wrong-length entry, a non-numeric value) raise a
    `TypeError`/`KeyError` deep inside a dict comprehension. Raises
    `ValueError` specifically (this project's own convention for "a value
    is present but nonsensical," `shared/config.py`'s validators) so the
    caller can distinguish "the peer sent garbage" from a genuine network
    failure and respond to each differently (`orchestrator_peer.py`'s
    finding — rule-auditor caught this before it shipped: an
    undifferentiated exception here was forcing *our own* technical loss
    whenever a hostile or buggy peer returned nonsense, rather than the
    malformed input being rejected gracefully).
    """
    if not isinstance(wire_data, dict) or not isinstance(wire_data.get("cells"), list):
        raise ValueError(f"scent-map payload missing a 'cells' list: {wire_data!r}")
    result: dict[Position, float] = {}
    for entry in wire_data["cells"]:
        if not isinstance(entry, (list, tuple)) or len(entry) != 3:
            raise ValueError(f"malformed scent-map cell entry: {entry!r}")
        col, row, value = entry
        if isinstance(col, bool) or not isinstance(col, int):
            raise ValueError(f"scent-map cell col must be an int, got {col!r}")
        if isinstance(row, bool) or not isinstance(row, int):
            raise ValueError(f"scent-map cell row must be an int, got {row!r}")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"scent-map cell value must be numeric, got {value!r}")
        result[Position(col, row)] = float(value)
    return result
