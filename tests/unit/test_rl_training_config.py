"""RLTrainingConfig: loads config/rl_training.toml, RL-only tunables, never
Appendix F territory (see that file's own header comment)."""

from __future__ import annotations

import pytest

from training.config import RLTrainingConfig

_VALID_DICT = {
    "episodes": {"episode_count": 2000, "seed": 0, "curriculum_switch_episode": 1000},
    "q_learning": {
        "alpha": 0.1,
        "gamma": 0.95,
        "epsilon_start": 1.0,
        "epsilon_end": 0.05,
        "epsilon_decay": 0.995,
    },
    "reward_shaping": {"distance_shaping_weight": 0.1, "step_cost": 0.01},
    "refinement": {
        "max_refinement_rounds": 3,
        "win_rate_target": 0.6,
        "wall_clock_budget_seconds": 300.0,
    },
}


def test_from_dict_reads_every_section():
    cfg = RLTrainingConfig.from_dict(_VALID_DICT)
    assert cfg.episode_count == 2000
    assert cfg.alpha == 0.1
    assert cfg.distance_shaping_weight == 0.1
    assert cfg.max_refinement_rounds == 3


def test_from_toml_loads_the_real_repo_config_file():
    cfg = RLTrainingConfig.from_toml("config/rl_training.toml")
    assert cfg.episode_count == 2000
    assert cfg.seed == 0
    assert cfg.win_rate_target == 0.6
    assert cfg.curriculum_switch_episode_2 == 1500
    assert cfg.curriculum_switch_episode_3 == 1800


def test_missing_section_raises_key_error():
    incomplete = {k: v for k, v in _VALID_DICT.items() if k != "refinement"}
    with pytest.raises(KeyError):
        RLTrainingConfig.from_dict(incomplete)


def test_missing_curriculum_switch_episode_2_defaults_to_stage_2_never_triggering():
    """PRD 14: a config file written before this field existed (exactly
    what _VALID_DICT's own `episodes` section already is, deliberately not
    updated above) must still load — falling back to `episode_count`, so
    the third curriculum stage simply never kicks in rather than raising."""
    cfg = RLTrainingConfig.from_dict(_VALID_DICT)
    assert cfg.curriculum_switch_episode_2 == cfg.episode_count


def test_missing_curriculum_switch_episode_3_defaults_to_stage_3_never_triggering():
    """PRD 14 round-2 post-gate: same backward-compat posture as
    curriculum_switch_episode_2 above — a config predating this field falls
    back to episode_count, so the fourth curriculum stage never kicks in."""
    cfg = RLTrainingConfig.from_dict(_VALID_DICT)
    assert cfg.curriculum_switch_episode_3 == cfg.episode_count
