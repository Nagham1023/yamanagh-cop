"""load_brain_class: Table 22's "package.module:Class" format, validated
and loaded — raises loudly on anything that isn't a real BrainBase
subclass, never silently falls back."""

from __future__ import annotations

import pytest

from cop.reasoning.cop_brain import CopBrain
from cop.reasoning.rl_cop_brain import RLCopBrain
from cop.shared.strategy_loader import load_brain_class


def test_loads_a_real_brain_base_subclass():
    assert load_brain_class("cop.reasoning.cop_brain:CopBrain") is CopBrain


def test_loads_rl_cop_brain_too():
    assert load_brain_class("cop.reasoning.rl_cop_brain:RLCopBrain") is RLCopBrain


def test_missing_colon_separator_raises():
    with pytest.raises(ValueError):
        load_brain_class("cop.reasoning.cop_brain.CopBrain")


def test_empty_string_raises():
    with pytest.raises(ValueError):
        load_brain_class("")


def test_missing_class_name_after_colon_raises():
    with pytest.raises(ValueError):
        load_brain_class("cop.reasoning.cop_brain:")


def test_missing_module_before_colon_raises():
    with pytest.raises(ValueError):
        load_brain_class(":CopBrain")


def test_unimportable_module_raises():
    with pytest.raises(ValueError):
        load_brain_class("cop.reasoning.this_module_does_not_exist:CopBrain")


def test_attribute_not_found_in_a_real_module_raises():
    with pytest.raises(ValueError):
        load_brain_class("cop.reasoning.cop_brain:ThisClassDoesNotExist")


def test_a_real_class_that_is_not_a_brain_base_subclass_raises():
    with pytest.raises(ValueError):
        load_brain_class("cop.domain.board:Board")
