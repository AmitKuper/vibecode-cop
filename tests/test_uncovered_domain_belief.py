"""Tests for domain/runtime_transition.py and synthetic_belief.py.

Split from test_uncovered_modules_coverage.py; no LLM, no network.
"""

import pytest


class TestRuntimeTransition:
    def test_illegal_joint_action_error_message(self):
        from cop_worker.domain.runtime_transition import IllegalJointActionError

        err = IllegalJointActionError(("cop",), "BADMOVE", "STAY")
        assert "cop" in str(err)
        assert "BADMOVE" in str(err)

    def test_locked_config_no_attr(self):
        from cop_worker.domain.config_validator import GameConfig
        from cop_worker.domain.runtime_transition import locked_config

        class FakeRuntime:
            pass

        cfg = locked_config(FakeRuntime())
        assert isinstance(cfg, GameConfig)

    def test_locked_config_with_game_config(self):
        from cop_worker.domain.config_validator import GameConfig
        from cop_worker.domain.runtime_transition import locked_config

        class FakeRuntime:
            game_config = GameConfig()  # defaults to grid_size=7 (Appendix F)

        cfg = locked_config(FakeRuntime())
        assert cfg.grid_size == 7


class TestSyntheticBelief:
    def test_get_belief_map_high_confidence(self):

        from cop_worker.synthetic_belief import SyntheticBeliefProvider

        sbp = SyntheticBeliefProvider()
        belief = sbp.get_belief_map(7, (3, 3), confidence_level="high")
        assert abs(belief.sum() - 1.0) < 0.01
        assert belief[3, 3] == pytest.approx(0.8)

    def test_get_belief_map_medium_confidence(self):
        from cop_worker.synthetic_belief import SyntheticBeliefProvider

        sbp = SyntheticBeliefProvider()
        belief = sbp.get_belief_map(7, (3, 3), confidence_level="medium")
        assert abs(belief.sum() - 1.0) < 0.01

    def test_get_belief_map_low_confidence(self):
        from cop_worker.synthetic_belief import SyntheticBeliefProvider

        sbp = SyntheticBeliefProvider()
        belief = sbp.get_belief_map(7, (3, 3), confidence_level="low")
        assert abs(belief.sum() - 1.0) < 0.01

    def test_get_belief_map_corner(self):
        from cop_worker.synthetic_belief import SyntheticBeliefProvider

        sbp = SyntheticBeliefProvider()
        belief = sbp.get_belief_map(7, (0, 0), confidence_level="high")
        # Corner has fewer neighbors but belief still sums to 1
        assert abs(belief.sum() - 1.0) < 0.01
