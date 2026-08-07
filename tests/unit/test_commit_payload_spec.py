"""integrity/commit_payload.py: PRD-6-prep-commit-payload-spec.md's frozen
`State` field list, enforced in code — byte-identical output across
differently-ordered construction paths, a real float rejection, and
stability across `PYTHONHASHSEED` (the one part of "ordering, not just
floats" worth confirming empirically rather than reasoning about from
CPython internals alone).
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from cop.domain.barriers import BarrierSet
from cop.domain.board import Position
from cop.integrity.commit_payload import _reject_floats, canonical_state_bytes
from cop.reasoning.state import GameState


def _game_state_with_barriers(barrier_positions: list[Position]) -> GameState:
    barriers = BarrierSet(quota=14)
    for pos in barrier_positions:
        barriers.placed.add(pos)
    return GameState(own_pos=Position(3, 3), target_pos=Position(0, 0), barriers=barriers, steps_taken=7)


def test_canonical_state_bytes_is_identical_across_hundreds_of_construction_orders():
    barrier_positions = [Position(1, 1), Position(2, 3), Position(0, 4), Position(5, 5)]
    reference = canonical_state_bytes(_game_state_with_barriers(barrier_positions))

    for seed in range(300):
        import random as _random  # local, deterministic per-iteration shuffle only

        shuffled = list(barrier_positions)
        _random.Random(seed).shuffle(shuffled)
        candidate = canonical_state_bytes(_game_state_with_barriers(shuffled))
        assert candidate == reference, f"construction order {shuffled!r} produced different bytes"


def test_canonical_state_bytes_excludes_target_pos_and_scent_belief():
    # target_pos differs but everything else is identical -> same bytes.
    # (scent_field/belief_map aren't GameState fields at all, so there's
    # nothing to accidentally include — this test pins the *other* belief
    # value, target_pos, which genuinely is a GameState field.)
    a = GameState(own_pos=Position(3, 3), target_pos=Position(0, 0), barriers=BarrierSet(quota=14), steps_taken=1)
    b = GameState(own_pos=Position(3, 3), target_pos=Position(6, 6), barriers=BarrierSet(quota=14), steps_taken=1)

    assert canonical_state_bytes(a) == canonical_state_bytes(b)


def test_canonical_state_bytes_is_valid_canonical_json_with_sorted_keys():
    state = _game_state_with_barriers([Position(2, 2)])
    payload = canonical_state_bytes(state)

    assert b" " not in payload  # separators=(",", ":") - no incidental whitespace
    assert payload.decode("utf-8").startswith('{"barriers_placed"')  # sort_keys=True: b < o < s alphabetically


def test_reject_floats_raises_on_a_nested_float():
    with pytest.raises(TypeError, match="contains a float"):
        _reject_floats({"own_pos": [3, 3], "scent_leak": 0.30000000000000004})


def test_reject_floats_accepts_ints_and_bools_without_raising():
    _reject_floats({"own_pos": [3, 3], "steps_taken": 7, "flag": True, "nested": [1, 2, {"x": False}]})


def test_canonical_state_bytes_is_stable_across_different_pythonhashseed_processes():
    # The specific hash-randomization risk this project has been careful
    # about elsewhere (PRD 4's nonce/string-hashing discipline) doesn't
    # apply to Position's int-based hash today (see the spec doc's
    # investigation) — confirmed here empirically, in two genuinely
    # separate OS processes, rather than trusted from reasoning alone.
    script = (
        "import sys; sys.path.insert(0, 'src'); "
        "from cop.domain.barriers import BarrierSet; "
        "from cop.domain.board import Position; "
        "from cop.integrity.commit_payload import canonical_state_bytes; "
        "from cop.reasoning.state import GameState; "
        "barriers = BarrierSet(quota=14); "
        "[barriers.placed.add(Position(c, r)) for c, r in [(1,1),(2,3),(0,4),(5,5)]]; "
        "state = GameState(own_pos=Position(3,3), target_pos=Position(0,0), barriers=barriers, steps_taken=7); "
        "sys.stdout.buffer.write(canonical_state_bytes(state))"
    )
    outputs = []
    for seed in ("0", "1", "1337"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        outputs.append(result.stdout)

    assert len(set(outputs)) == 1, f"output varied across PYTHONHASHSEED: {outputs!r}"
