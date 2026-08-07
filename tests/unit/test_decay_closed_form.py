"""Rule 23's sanction is that a decay-formula deviation voids the game —
this proves the closed form rather than assuming it. The book decays
after *both* agents move; this repo has each peer own one field and
`advance()` it once per its own turn (PRD 4 Revision 1, Design Question
1) — those coincide only if `advance()`'s repeated-decay arithmetic
actually matches `source * (1-rho)^N`, checked here to a stated
tolerance, then confirmed identical across two genuinely separate OS
processes (not just "the same process ran it twice").
"""

from __future__ import annotations

import os
import subprocess
import sys

from cop.domain.board import Board, Position
from cop.memory.scent import ScentField

_TOLERANCE = 1e-9


def test_residual_after_n_turns_of_pure_decay_matches_the_closed_form(config):
    board = Board(size=config.board_size)
    field = ScentField.from_config(config)
    true_pos = Position(3, 3)
    far_pos = Position(config.board_size - 1, config.board_size - 1)

    field.advance(true_pos, board)  # a single emission
    n = 10
    for _ in range(n):
        field.advance(far_pos, board)  # decay only — far_pos's kernel never reaches true_pos

    residual = field.sample(true_pos, board)[true_pos]
    expected = config.scent_source_strength * (1 - config.scent_decay_rate) ** n

    assert abs(residual - expected) < _TOLERANCE, f"residual={residual!r} expected={expected!r}"


def test_residual_matches_the_closed_form_at_every_n_from_1_to_20(config):
    # A single N could pass by coincidence if advance() over/under-decays
    # in a way that happens to cancel out at exactly one step count — check
    # the whole curve, not one point on it.
    board = Board(size=config.board_size)
    field = ScentField.from_config(config)
    true_pos = Position(3, 3)
    far_pos = Position(config.board_size - 1, config.board_size - 1)
    field.advance(true_pos, board)

    for n in range(1, 21):
        field.advance(far_pos, board)
        residual = field.sample(true_pos, board)[true_pos]
        expected = config.scent_source_strength * (1 - config.scent_decay_rate) ** n
        assert abs(residual - expected) < _TOLERANCE, f"n={n}: residual={residual!r} expected={expected!r}"


_CROSS_PROCESS_SCRIPT = """
import sys
sys.path.insert(0, "src")
from cop.domain.board import Board, Position
from cop.memory.scent import ScentField
from cop.shared.config import GameConfig

config = GameConfig.from_file("config/shared/config_dev_g01.json")
board = Board(size=config.board_size)
field = ScentField.from_config(config)
true_pos = Position(3, 3)
far_pos = Position(config.board_size - 1, config.board_size - 1)

field.advance(true_pos, board)
for _ in range(10):
    field.advance(far_pos, board)

residual = field.sample(true_pos, board)[true_pos]
sys.stdout.write(repr(residual))
"""


def test_two_real_os_processes_compute_the_identical_residual_at_the_same_step():
    outputs = []
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "-c", _CROSS_PROCESS_SCRIPT],
            capture_output=True,
            check=True,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            text=True,
        )
        outputs.append(result.stdout)

    assert outputs[0] == outputs[1], f"the two processes disagreed: {outputs!r}"
