"""Tabular Q-learning and dueling Double-DQN research on canonical physics (see submodules)."""

from cop_worker.rl.research_value_training.cli import main
from cop_worker.rl.research_value_training.ddqn import train_ddqn
from cop_worker.rl.research_value_training.networks import (
    DQNResearchPolicy,
    DuelingDoubleQNetwork,
    _actions,
    load_dqn_policy,
)
from cop_worker.rl.research_value_training.qtable import (
    TabularResearchPolicy,
    _q_key,
    train_q_table,
)
from cop_worker.rl.research_value_training.replay import ReplayBuffer, ReplayItem
from cop_worker.rl.research_value_training.shaping import (
    _default_population,
    _expected_distance,
    _frozen_opponent,
    _local_shaping,
    _terminal_reward,
    _update_beliefs,
)
from cop_worker.rl.research_value_training.updates import _ddqn_update, _masked_epsilon_action

__all__ = [
    "DQNResearchPolicy",
    "DuelingDoubleQNetwork",
    "ReplayBuffer",
    "ReplayItem",
    "TabularResearchPolicy",
    "_actions",
    "_ddqn_update",
    "_default_population",
    "_expected_distance",
    "_frozen_opponent",
    "_local_shaping",
    "_masked_epsilon_action",
    "_q_key",
    "_terminal_reward",
    "_update_beliefs",
    "load_dqn_policy",
    "main",
    "train_ddqn",
    "train_q_table",
]
