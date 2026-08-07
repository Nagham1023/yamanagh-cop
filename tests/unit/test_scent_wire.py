"""tools/scent_wire.py: ScentField.full_field() <-> the wire-safe MCP tool
payload (todoFullFix.md §C2, PRD 4 "Revision 3")."""

from __future__ import annotations

import json

import pytest

from cop.domain.board import Board, Position
from cop.memory.scent import ScentField
from cop.tools.scent_wire import deserialize_scent_field, serialize_scent_field


def test_round_trip_preserves_every_cell_and_value_exactly(config):
    field = ScentField.from_config(config)
    board = Board(size=config.board_size)
    field.advance(Position(1, 1), board)
    field.advance(Position(5, 5), board)
    original = field.full_field()

    wire = serialize_scent_field(original)
    recovered = deserialize_scent_field(wire)

    assert recovered == original


def test_wire_shape_is_json_serializable_and_has_only_the_cells_key(config):
    field = ScentField.from_config(config)
    board = Board(size=config.board_size)
    field.advance(Position(3, 3), board)

    wire = serialize_scent_field(field.full_field())

    assert set(wire.keys()) == {"cells"}
    json.dumps(wire)  # must not raise — a Position key would break this


def test_empty_field_serializes_to_an_empty_cell_list():
    assert serialize_scent_field({}) == {"cells": []}
    assert deserialize_scent_field({"cells": []}) == {}


def test_wire_payload_never_leaks_anything_but_numeric_scent_cells(config):
    # "Grep the wire" (PRD 4's own discipline, reused): every entry in
    # "cells" must be exactly [col, row, value] — three numbers, nothing
    # that could carry a GameState field (own_pos claim, barriers, text)
    # riding along inside the scent-map tool's payload.
    field = ScentField.from_config(config)
    board = Board(size=config.board_size)
    field.advance(Position(2, 4), board)

    wire = serialize_scent_field(field.full_field())

    for entry in wire["cells"]:
        assert len(entry) == 3
        col, row, value = entry
        assert isinstance(col, int)
        assert isinstance(row, int)
        assert isinstance(value, float)


# Rule 9 (CLAUDE.md) — everything a peer sends is untrusted: a malformed
# share_scent_map response must be rejected with a clear ValueError, not
# raise a confusing TypeError/KeyError deep inside a dict comprehension,
# and specifically must be a *different* exception type than a network
# failure so the caller (orchestrator_peer.py) can tell them apart —
# rule-auditor finding, found before this shipped.


def test_missing_cells_key_is_rejected():
    with pytest.raises(ValueError, match="cells"):
        deserialize_scent_field({})


def test_non_list_cells_is_rejected():
    with pytest.raises(ValueError, match="cells"):
        deserialize_scent_field({"cells": "not a list"})


def test_wrong_length_entry_is_rejected():
    with pytest.raises(ValueError, match="malformed"):
        deserialize_scent_field({"cells": [[1, 2]]})


def test_non_integer_col_is_rejected():
    with pytest.raises(ValueError, match="col"):
        deserialize_scent_field({"cells": [["not an int", 2, 0.9]]})


def test_non_integer_row_is_rejected():
    with pytest.raises(ValueError, match="row"):
        deserialize_scent_field({"cells": [[1, "not an int", 0.9]]})


def test_non_numeric_value_is_rejected():
    with pytest.raises(ValueError, match="value"):
        deserialize_scent_field({"cells": [[1, 2, "not a number"]]})


def test_boolean_col_is_rejected_not_silently_accepted_as_an_int():
    # isinstance(True, int) is True in Python — a real footgun this
    # validator must not fall into (same guard shared/config.py's own
    # validators already use for the same reason).
    with pytest.raises(ValueError, match="col"):
        deserialize_scent_field({"cells": [[True, 2, 0.9]]})
