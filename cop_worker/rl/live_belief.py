"""Live-belief serving adapter for policies trained WITHOUT the frozen uniform prior.

Every artifact records in its manifest ``obs_mode`` whether it trained on the frozen
uniform belief (``uniform_belief: true`` — the historical production default) or on
the live Bayesian filter. This adapter is applied by ``load_counted_policy`` ONLY
when the manifest says ``uniform_belief: false``; every existing uniform-belief
artifact takes the unchanged legacy path, so behavior for current champions is
byte-identical.

The update order mirrors training (``train_recurrent.episode_steps._advance_beliefs``):
each serving call first advances the filter with the barriers and the freshly
observed opponent scent, then feeds the posterior to the network. ``reset()``
discards the filter — one sub-game is one episode (pinned by
tests/test_serving_episode_reset.py; this adapter is covered by
tests/test_live_belief_serving.py).
"""

from __future__ import annotations

from cop_worker.observation import BeliefState, LocalObservation


class LiveBeliefPolicy:
    """Substitute the caller's (uniform) belief with a live per-episode filter."""

    def __init__(self, inner, role: str) -> None:
        self.inner = inner
        self.role = role
        self._engine = None

    def reset(self) -> None:
        self._engine = None
        self.inner.reset()

    def _advance(self, observation: LocalObservation):
        from cop_worker.belief_engine import BeliefEngine

        if self._engine is None:
            self._engine = BeliefEngine(observation.grid_size, self.role)
        barriers = [tuple(cell) for cell in observation.known_barriers]
        self._engine = self._engine.predict(barriers).observe_scent(
            observation.opponent_scent, barriers
        )
        return self._engine.belief

    def select_action(
        self,
        observation: LocalObservation,
        belief: BeliefState,
        legal_actions: list[str],
    ) -> str:
        live = self._advance(observation)
        return self.inner.select_action(observation, live, legal_actions)


def wants_live_belief(entry) -> bool:
    """True when the manifest records the artifact as trained on the live filter."""
    recorded = dict(getattr(entry, "obs_mode", None) or {})
    return recorded.get("uniform_belief") is False
