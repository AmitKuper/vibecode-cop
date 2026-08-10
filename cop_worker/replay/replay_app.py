"""Step-0-anchored canonical replay and tamper verification (+ReplayViewer re-export)."""

from __future__ import annotations

from pathlib import Path

from cop_worker.audit.result_consensus import GameletOutcome, ResultAgreement
from cop_worker.audit.step_journal import StepJournal
from cop_worker.config.shared_config import config_sha256
from cop_worker.domain.config_validator import game_config_from_dict
from cop_worker.domain.types import DomainState
from cop_worker.replay.replay_reconstruct import ReplayReconstructMixin
from cop_worker.replay.replay_stepview import ReplayViewer  # noqa: F401  (re-export)
from cop_worker.replay.replay_types import _GAMELETS, ReplayError, ReplayState  # noqa: F401
from cop_worker.replay.replay_verify import ReplayVerifyMixin


class ReplayApp(ReplayVerifyMixin, ReplayReconstructMixin):
    """Verify trusted identities, evidence, and every configured transition."""

    def __init__(self):
        self._result: ResultAgreement | None = None
        self._journals: dict[int, StepJournal] = {}
        self._states: dict[int, list[DomainState]] = {}
        self._verified = False
        self._tamper_reason = ""
        self._current_gamelet = 1
        self._current_step = 0

    def load(
        self,
        result_path: str,
        journal_paths: dict[int, str],
        *,
        trusted_step0_paths: dict[int, str],
        config_path: str,
    ) -> bool:
        """Verify a counted six-gamelet result and reconstruct every transition."""
        self._verified = False
        self._tamper_reason = ""
        self._journals = {}
        self._states = {}
        try:
            artifact = self._read_json(result_path)
            agreement_data = dict(artifact["agreement"])
            agreement_data["gamelet_outcomes"] = [
                GameletOutcome(**item) for item in agreement_data.get("gamelet_outcomes", [])
            ]
            self._result = ResultAgreement(**agreement_data)
            if not self._result.counted_status:
                raise ReplayError("replay artifact is not a counted result")
            if set(journal_paths) != _GAMELETS or set(trusted_step0_paths) != _GAMELETS:
                raise ReplayError("expected exact gamelet keys {1,2,3,4,5,6}")
            outcomes = {item.gamelet: item for item in self._result.gamelet_outcomes}
            if set(outcomes) != _GAMELETS or len(self._result.gamelet_outcomes) != 6:
                raise ReplayError("signed result is not exactly gamelets 1..6")

            raw_config = self._read_json(config_path)
            if (
                not self._result.config_hash
                or config_sha256(raw_config) != self._result.config_hash
            ):
                raise ReplayError("trusted config does not match signed result")
            config = game_config_from_dict(raw_config)
            step0 = {
                gamelet: self._verified_step0(path) for gamelet, path in trusted_step0_paths.items()
            }
            self._verify_result_signatures(
                self._result,
                artifact,
                (step0[6][0], step0[6][1]),
            )
            for gamelet in sorted(_GAMELETS):
                path = Path(journal_paths[gamelet])
                if not path.is_file():
                    raise ReplayError(f"gamelet {gamelet} journal is missing")
                journal = StepJournal(str(path))
                self._states[gamelet] = self._reconstruct_gamelet(
                    gamelet, journal, outcomes[gamelet], step0[gamelet], config
                )
                self._journals[gamelet] = journal

            if sum(item.cop_score for item in outcomes.values()) != self._result.cop_total_score:
                raise ReplayError("cop series total mismatch")
            if (
                sum(item.thief_score for item in outcomes.values())
                != self._result.thief_total_score
            ):
                raise ReplayError("thief series total mismatch")
            expected_series = (
                "cop"
                if self._result.cop_total_score > self._result.thief_total_score
                else "thief"
                if self._result.thief_total_score > self._result.cop_total_score
                else "draw"
            )
            if self._result.series_winner != expected_series:
                raise ReplayError("series winner mismatch")
        except Exception as exc:
            self._tamper_reason = str(exc)
            return False

        self._verified = True
        self._current_gamelet = 1
        self._current_step = 0
        return True

    def verification_status(self) -> tuple[bool, str]:
        return self._verified, self._tamper_reason

    def current_state(self) -> ReplayState:
        journal = self._journals.get(self._current_gamelet)
        entries = journal.entries if journal else []
        event = entries[self._current_step] if 0 <= self._current_step < len(entries) else None
        states = self._states.get(self._current_gamelet, [])
        domain = states[self._current_step + 1] if event is not None and states else None
        return ReplayState(
            game_uid=self._result.game_uid if self._result else "",
            gamelet=self._current_gamelet,
            step=self._current_step,
            total_steps=len(entries),
            event=event,
            verified=self._verified,
            tamper_reason=self._tamper_reason,
            transcript_verified=self._verified,
            canonical_state=domain.model_dump(mode="json") if domain is not None else None,
        )

    def next(self) -> ReplayState:
        journal = self._journals.get(self._current_gamelet)
        if journal and self._current_step < len(journal.entries) - 1:
            self._current_step += 1
        return self.current_state()

    def prev(self) -> ReplayState:
        if self._current_step > 0:
            self._current_step -= 1
        return self.current_state()

    def first(self) -> ReplayState:
        self._current_step = 0
        return self.current_state()

    def last(self) -> ReplayState:
        journal = self._journals.get(self._current_gamelet)
        if journal:
            self._current_step = max(0, len(journal.entries) - 1)
        return self.current_state()
