"""RLTrainingConfig: RL-only tunables (`config/rl_training.toml`), never
Appendix F territory — see that file's own header comment for why. Kept as
a separate, small dataclass rather than folded into `GameConfig`, the same
split `PrivateConfig` already keeps for `config/game.toml` (this repo's own
precedent for "negotiated game rules" vs. "private/algorithm tuning" living
in genuinely separate loaders, not just separate config files).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RLTrainingConfig:
    episode_count: int
    seed: int
    curriculum_switch_episode: int
    curriculum_switch_episode_2: int
    alpha: float
    gamma: float
    epsilon_start: float
    epsilon_end: float
    epsilon_decay: float
    distance_shaping_weight: float
    step_cost: float
    barrier_restriction_bonus_weight: float
    max_refinement_rounds: int
    win_rate_target: float
    wall_clock_budget_seconds: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RLTrainingConfig:
        episodes = data["episodes"]
        q_learning = data["q_learning"]
        reward_shaping = data["reward_shaping"]
        refinement = data["refinement"]
        return cls(
            episode_count=episodes["episode_count"],
            seed=episodes["seed"],
            curriculum_switch_episode=episodes["curriculum_switch_episode"],
            # PRD 14: a third, harder curriculum stage. Defaulted via .get()
            # so a config file written before this field existed still loads
            # — falls back to episode_count (never reached, i.e. stage 2
            # never kicks in), the same "absent means off" posture the rest
            # of this dataclass avoids only because every other field here
            # predates having an optional one.
            curriculum_switch_episode_2=episodes.get(
                "curriculum_switch_episode_2", episodes["episode_count"]
            ),
            alpha=float(q_learning["alpha"]),
            gamma=float(q_learning["gamma"]),
            epsilon_start=float(q_learning["epsilon_start"]),
            epsilon_end=float(q_learning["epsilon_end"]),
            epsilon_decay=float(q_learning["epsilon_decay"]),
            distance_shaping_weight=float(reward_shaping["distance_shaping_weight"]),
            step_cost=float(reward_shaping["step_cost"]),
            # PRD 14 post-gate follow-up: absent means 0.0 (no behavior
            # change), same "config predates this field" backward-compat
            # posture curriculum_switch_episode_2 already established above.
            barrier_restriction_bonus_weight=float(
                reward_shaping.get("barrier_restriction_bonus_weight", 0.0)
            ),
            max_refinement_rounds=refinement["max_refinement_rounds"],
            win_rate_target=float(refinement["win_rate_target"]),
            wall_clock_budget_seconds=float(refinement["wall_clock_budget_seconds"]),
        )

    @classmethod
    def from_toml(cls, path: str | Path) -> RLTrainingConfig:
        raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(raw)
