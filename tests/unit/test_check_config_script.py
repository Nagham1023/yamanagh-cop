"""check_config.py's own rejection test — todoFullFix.md §A4.

The nested-schema migration (§A1-A3) could have quietly weakened the
validator (e.g. by making `flatten()`/`lookup()` tolerant of a missing
group). This proves it didn't: a config missing a whole mandatory nested
group still fails clearly, the same "write at least one test per layer
that proves rejection" discipline as every other layer in this repo.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / ".claude/skills/spec-guard/scripts/check_config.py"
_spec = importlib.util.spec_from_file_location("check_config", _SCRIPT_PATH)
check_config = importlib.util.module_from_spec(_spec)
sys.modules["check_config"] = check_config
_spec.loader.exec_module(check_config)


def test_real_dev_config_passes_clean():
    import json

    config = json.loads(Path("config/shared/config_dev_g01.json").read_text(encoding="utf-8"))
    result = check_config.check(config)
    assert result["violations"] == []


def test_missing_mandatory_group_is_a_violation_not_a_silent_pass():
    # No board_and_agents, movement_and_barriers, pheromones, or scoring at
    # all — every FIXED/MINIMUM param in those groups must be reported
    # missing, not silently treated as "absent NEGOTIABLE, default applies".
    config = {"schema_version": "1.2", "agreed_between": ["a", "b"]}

    result = check_config.check(config)

    violation_params = {v["param"] for v in result["violations"]}
    assert "board_size" in violation_params
    assert "barrier_quota" in violation_params
    assert "scent_source_strength" in violation_params
    assert all(v["rule"] == "missing" for v in result["violations"] if v["param"] in violation_params)


def test_nested_book_leaf_names_are_found_by_the_validator():
    # The validator's flatten()+lookup() must find Appendix B's real nested
    # names (grid_size under board_and_agents, pheromone_center_intensity
    # under pheromones, ...) — not just this skill's own internal aliases.
    config = {
        "board_and_agents": {"grid_size": 9},  # raised above the MINIMUM, legal
        "pheromones": {"pheromone_center_intensity": 0.9},
    }

    result = check_config.check(config)

    violation_params = {v["param"] for v in result["violations"]}
    assert "board_size" not in violation_params
    assert "scent_source_strength" not in violation_params
