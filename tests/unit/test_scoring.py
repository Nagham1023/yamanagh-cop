"""Table 17 scoring: every outcome maps to the config-driven (cop, thief) pair."""

from __future__ import annotations

from cop.domain.scoring import Outcome, Score, score_outcome


def test_capture_scores_cop_high_thief_low(config):
    assert score_outcome(Outcome.CAPTURE, config) == Score(cop=20, thief=5)


def test_survival_scores_thief_high_cop_low(config):
    assert score_outcome(Outcome.SURVIVAL, config) == Score(cop=5, thief=10)


def test_technical_loss_scores_zero_to_both(config):
    assert score_outcome(Outcome.TECHNICAL_LOSS, config) == Score(cop=0, thief=0)


def test_technical_loss_score_is_never_read_from_config(config):
    # Deliberately mangle the config's other values to prove technical-loss
    # scoring is hard-fixed at (0, 0) and not accidentally sourced from config.
    tampered = config.__class__(**{**config.__dict__, "score_capture_cop": 999})
    assert score_outcome(Outcome.TECHNICAL_LOSS, tampered) == Score(cop=0, thief=0)
