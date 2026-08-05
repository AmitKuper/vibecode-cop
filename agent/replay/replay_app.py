"""Anchored Replay App — forward/backward navigation, VERIFIED OK or TAMPERED."""

import json
from dataclasses import dataclass

from agent.audit.result_consensus import GameletOutcome, ResultAgreement, SignedResultAgreement
from agent.audit.step_journal import StepEvidence, StepJournal
from agent.step0.signing import verify as verify_sig


@dataclass
class ReplayState:
    game_uid: str
    gamelet: int
    step: int
    total_steps: int
    event: StepEvidence | None
    verified: bool
    tamper_reason: str
    transcript_verified: bool


class ReplayError(ValueError):
    pass


class ReplayApp:
    """Loads signed result, verifies chain, allows step navigation."""

    def __init__(self):
        self._result: SignedResultAgreement | None = None
        self._journals: dict[int, StepJournal] = {}
        self._verified = False
        self._tamper_reason = ""
        self._current_gamelet = 1
        self._current_step = 0

    def load(self, result_path: str, journal_paths: dict[int, str]) -> bool:
        """Load and verify. Returns True if valid."""
        try:
            with open(result_path) as f:
                data = json.load(f)
            agreement_data = dict(data["agreement"])
            agreement_data["gamelet_outcomes"] = [
                GameletOutcome(**o) for o in agreement_data.get("gamelet_outcomes", [])
            ]
            agreement = ResultAgreement(**agreement_data)
            self._result = SignedResultAgreement(agreement, data["signature_hex"])
        except Exception as e:
            self._tamper_reason = f"Failed to load result: {e}"
            return False

        # Verify result signature
        try:
            pub_bytes = bytes.fromhex(self._result.agreement.public_key_hex)
            sig_bytes = bytes.fromhex(self._result.signature_hex)
            if not verify_sig(pub_bytes, self._result.agreement.canonical_bytes(), sig_bytes):
                self._tamper_reason = "Result signature invalid"
                return False
        except Exception as e:
            self._tamper_reason = f"Signature verification failed: {e}"
            return False

        # Counted matches require exactly 6 gamelet journals.
        if len(journal_paths) != 6:
            self._tamper_reason = f"Expected exactly 6 gamelet journals, got {len(journal_paths)}"
            return False

        # Load and verify each gamelet journal; compare transcript root to signed result.
        gamelet_outcomes = {
            go.gamelet: go
            for go in (self._result.agreement.gamelet_outcomes if self._result else [])
        }
        for gamelet, path in journal_paths.items():
            try:
                journal = StepJournal(path)
                ok, err = journal.verify_chain()
                if not ok:
                    self._tamper_reason = f"Gamelet {gamelet} chain broken: {err}"
                    return False
                outcome = gamelet_outcomes.get(gamelet)
                if outcome is not None and outcome.transcript_root:
                    journal_root = journal.transcript_root()
                    if journal_root != outcome.transcript_root:
                        self._tamper_reason = (
                            f"Gamelet {gamelet} transcript_root mismatch: "
                            f"journal={journal_root} signed={outcome.transcript_root}"
                        )
                        return False
                self._journals[gamelet] = journal
            except Exception as e:
                self._tamper_reason = f"Failed to load gamelet {gamelet}: {e}"
                return False

        self._verified = True
        self._current_gamelet = min(self._journals.keys()) if self._journals else 1
        self._current_step = 0
        return True

    def verification_status(self) -> tuple[bool, str]:
        return self._verified, self._tamper_reason

    def current_state(self) -> ReplayState:
        journal = self._journals.get(self._current_gamelet)
        entries = journal.entries if journal else []
        event = entries[self._current_step] if 0 <= self._current_step < len(entries) else None
        return ReplayState(
            game_uid=self._result.agreement.game_uid if self._result else "",
            gamelet=self._current_gamelet,
            step=self._current_step,
            total_steps=len(entries),
            event=event,
            verified=self._verified,
            tamper_reason=self._tamper_reason,
            transcript_verified=self._verified,
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
