"""Train and evaluate the deployed recurrent local-observation policy.

Package layout (split from the original single module; the public surface is
unchanged — import everything from ``cop_worker.rl.train_recurrent`` exactly as
before, including the historically patchable helpers):

- ``schedules``   opponent families and role curricula
- ``sim``         domain-state helpers and dense rewards
- ``expert``      the local-only belief teacher
- ``opponents``   scripted opponent families (+ ``opponents_historical``)
- ``observation`` policy-side tensor and action-mask construction
- ``episode``     single-episode rollout (+ ``episode_steps``)
- ``imitation``   behaviour-cloning warm start
- ``training``    the recurrent A2C loop
- ``evaluation``  the held-out six-gamelet tournament
- ``stats``       Wilson intervals and the promotion gate
- ``cli``         the ``python -m cop_worker.rl.train_recurrent`` entry point

Cross-module calls to the patchable helpers go through this package object at
call time, so ``monkeypatch.setattr("cop_worker.rl.train_recurrent.<name>", ...)``
keeps affecting the internal callers exactly as it did with the single file.
"""

from cop_worker.rl.train_recurrent.episode import _run_episode
from cop_worker.rl.train_recurrent.evaluation import evaluate
from cop_worker.rl.train_recurrent.expert import _belief_expert_action
from cop_worker.rl.train_recurrent.imitation import _collect_demonstrations, _pretrain_imitation
from cop_worker.rl.train_recurrent.observation import _observation
from cop_worker.rl.train_recurrent.opponents import _opponent_action
from cop_worker.rl.train_recurrent.schedules import (
    COP_TRAINING_SCHEDULE,
    FAMILIES,
    THIEF_TRAINING_SCHEDULE,
    WORST_FAMILY_PROMOTION_FLOOR,
)
from cop_worker.rl.train_recurrent.sim import (
    _action_position,
    _belief_trap_reward,
    _distance,
    _initial_state,
    _legal,
    _local_exit_count,
)
from cop_worker.rl.train_recurrent.stats import _promotion_comparison, _wilson
from cop_worker.rl.train_recurrent.training import train


def main() -> None:
    from cop_worker.rl.train_recurrent.cli import main as _cli_main

    _cli_main()


__all__ = [
    "COP_TRAINING_SCHEDULE",
    "FAMILIES",
    "THIEF_TRAINING_SCHEDULE",
    "WORST_FAMILY_PROMOTION_FLOOR",
    "_action_position",
    "_belief_expert_action",
    "_belief_trap_reward",
    "_collect_demonstrations",
    "_distance",
    "_initial_state",
    "_legal",
    "_local_exit_count",
    "_observation",
    "_opponent_action",
    "_pretrain_imitation",
    "_promotion_comparison",
    "_run_episode",
    "_wilson",
    "evaluate",
    "main",
    "train",
]
