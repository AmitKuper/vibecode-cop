"""Tests for rl/networks.py and rl/observation.py.

Split from test_uncovered_modules_coverage.py; no LLM, no network.
"""


class TestNetworks:
    def test_mlp_backbone_forward(self):
        import torch

        from cop_worker.rl.networks import _MLPBackbone

        net = _MLPBackbone(grid_size=7, in_channels=4, hidden=64)
        x = torch.zeros(2, 4, 7, 7)
        out = net(x)
        assert out.shape == (2, 64)

    def test_cnn_backbone_forward(self):
        import torch

        from cop_worker.rl.networks import _CNNBackbone

        net = _CNNBackbone(grid_size=7, in_channels=4, hidden=64)
        x = torch.zeros(2, 4, 7, 7)
        out = net(x)
        assert out.shape == (2, 64)

    def test_dqn_net_forward(self):
        import torch

        from cop_worker.rl.networks import DQNNet

        net = DQNNet(grid_size=7, n_actions=5, hidden=32, net_type="mlp")
        x = torch.zeros(1, 4, 7, 7)
        q = net(x)
        assert q.shape == (1, 5)

    def test_dqn_net_cnn(self):
        import torch

        from cop_worker.rl.networks import DQNNet

        net = DQNNet(grid_size=7, n_actions=5, hidden=32, net_type="cnn")
        x = torch.zeros(1, 4, 7, 7)
        q = net(x)
        assert q.shape == (1, 5)

    def test_ppo_net_forward(self):
        import torch

        from cop_worker.rl.networks import PPONet

        net = PPONet(grid_size=7, n_actions=5, hidden=32)
        x = torch.zeros(1, 4, 7, 7)
        logits, value = net(x)
        assert logits.shape == (1, 5)
        assert value.shape == (1, 1)

    def test_ppo_net_get_action(self):
        import torch

        from cop_worker.rl.networks import PPONet

        net = PPONet(grid_size=7, n_actions=5, hidden=32)
        x = torch.zeros(1, 4, 7, 7)
        action, log_prob, entropy, value = net.get_action(x, deterministic=True)
        assert 0 <= action.item() < 5
        action2, _, _, _ = net.get_action(x, deterministic=False)
        assert 0 <= action2.item() < 5


class TestObservation:
    def _make_board(self, grid_size=7, cop=(0, 0), thief=(3, 3), barriers=None, turn=1):
        from cop_worker.board import Board

        board = Board(
            cop_position=list(cop),
            thief_position=list(thief),
            grid_size=grid_size,
            barriers=[list(b) for b in (barriers or [])],
            turn=turn,
        )
        return board

    def test_cop_observation_shape(self):
        from cop_worker.rl.observation import cop_observation
        from cop_worker.rules_engine import RulesEngine

        board = self._make_board()
        rules = RulesEngine(board)
        obs = cop_observation(board, rules, max_steps=35)
        assert len(obs) == 4
        assert len(obs[0]) == 7
        assert len(obs[0][0]) == 7

    def test_cop_observation_with_barriers(self):
        from cop_worker.rl.observation import cop_observation
        from cop_worker.rules_engine import RulesEngine

        board = self._make_board(barriers=[(1, 0)])
        rules = RulesEngine(board)
        obs = cop_observation(board, rules, max_steps=35, barrier_quota=5, barriers_remaining=3)
        assert len(obs) == 5  # extra barrier quota channel

    def test_thief_observation_shape(self):
        from cop_worker.rl.observation import thief_observation

        board = self._make_board()
        obs = thief_observation(board, max_steps=35)
        assert len(obs) == 4

    def test_thief_observation_with_scent(self):
        from cop_worker.rl.observation import local_thief_observation

        board = self._make_board()
        scent = [[0.1] * 7 for _ in range(7)]
        obs = local_thief_observation(board, max_steps=35, cop_scent_field=scent)
        assert obs[1] == scent

    def test_observation_shape_function(self):
        from cop_worker.rl.observation import observation_shape

        assert observation_shape(7, "thief") == (4, 7, 7)
        assert observation_shape(7, "cop", barrier_quota=0) == (4, 7, 7)
        assert observation_shape(7, "cop", barrier_quota=5) == (5, 7, 7)
