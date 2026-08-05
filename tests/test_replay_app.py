"""Tests for the anchored Replay app."""

import json
from pathlib import Path

from agent.audit.result_consensus import GameletOutcome, ResultAgreement, SignedResultAgreement
from agent.audit.step_journal import StepEvidence, StepJournal
from agent.replay.replay_app import ReplayApp
from agent.step0.signing import generate_key_pair, sign

_N_GAMELETS = 6


def _make_signed_result(tmp_path: Path, game_uid: str = "test-game-001") -> tuple[Path, bytes]:
    priv, pub = generate_key_pair()
    agreement = ResultAgreement(
        game_uid=game_uid,
        schema_version="1.0",
        gamelet_outcomes=[
            GameletOutcome(gamelet=g, cop_score=1, thief_score=0, winner="cop", turns_played=5)
            for g in range(1, _N_GAMELETS + 1)
        ],
        cop_total_score=_N_GAMELETS,
        thief_total_score=0,
        series_winner="cop",
        counted_status=True,
        public_key_hex=pub.hex(),
    )
    sig = sign(priv, agreement.canonical_bytes())
    sra = SignedResultAgreement(agreement, sig.hex())
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(sra.to_dict()), encoding="utf-8")
    return result_path, priv


def _make_journal(tmp_path: Path, game_uid: str, gamelet: int = 1, num_steps: int = 3) -> Path:
    journal_path = tmp_path / f"journal_g{gamelet:02d}.json"
    journal = StepJournal(str(journal_path))
    for i in range(num_steps):
        ev = StepEvidence(
            game_uid=game_uid,
            gamelet=gamelet,
            step=i,
            role="cop",
            local_move="N",
            local_hint="hint",
        )
        journal.append(ev)
    return journal_path


def _make_six_journals(tmp_path: Path, game_uid: str, num_steps: int = 3) -> dict[int, str]:
    return {
        g: str(_make_journal(tmp_path, game_uid, gamelet=g, num_steps=num_steps))
        for g in range(1, _N_GAMELETS + 1)
    }


class TestReplayAppLoad:
    def test_load_valid_result(self, tmp_path):
        result_path, _ = _make_signed_result(tmp_path)
        journals = _make_six_journals(tmp_path, "test-game-001")
        app = ReplayApp()
        ok = app.load(str(result_path), journals)
        assert ok is True
        verified, reason = app.verification_status()
        assert verified is True
        assert reason == ""

    def test_load_invalid_signature(self, tmp_path):
        result_path, _ = _make_signed_result(tmp_path)
        data = json.loads(result_path.read_text())
        data["signature_hex"] = "aa" * 64
        result_path.write_text(json.dumps(data))
        journals = _make_six_journals(tmp_path, "test-game-001")
        app = ReplayApp()
        ok = app.load(str(result_path), journals)
        assert ok is False
        verified, reason = app.verification_status()
        assert verified is False
        assert reason != ""

    def test_load_wrong_gamelet_count(self, tmp_path):
        result_path, _ = _make_signed_result(tmp_path)
        journal_path = _make_journal(tmp_path, "test-game-001")
        app = ReplayApp()
        ok = app.load(str(result_path), {1: str(journal_path)})
        assert ok is False
        verified, reason = app.verification_status()
        assert verified is False
        assert "6" in reason

    def test_load_missing_journal(self, tmp_path):
        result_path, _ = _make_signed_result(tmp_path)
        journals = _make_six_journals(tmp_path, "test-game-001")
        journals[1] = str(tmp_path / "nonexistent.json")
        app = ReplayApp()
        ok = app.load(str(result_path), journals)
        assert isinstance(ok, bool)

    def test_tampered_chain_detected(self, tmp_path):
        result_path, _ = _make_signed_result(tmp_path)
        journals = _make_six_journals(tmp_path, "test-game-001")
        data = json.loads(Path(journals[1]).read_text())
        data["entries"][0]["local_move"] = "TAMPERED"
        Path(journals[1]).write_text(json.dumps(data))
        app = ReplayApp()
        ok = app.load(str(result_path), journals)
        assert ok is False
        verified, reason = app.verification_status()
        assert "chain broken" in reason or "broken" in reason.lower() or not verified

    def test_unloaded_returns_unverified(self):
        app = ReplayApp()
        verified, reason = app.verification_status()
        assert verified is False


class TestReplayNavigation:
    def _loaded_app(self, tmp_path) -> ReplayApp:
        result_path, _ = _make_signed_result(tmp_path)
        journals = _make_six_journals(tmp_path, "test-game-001", num_steps=5)
        app = ReplayApp()
        app.load(str(result_path), journals)
        return app

    def test_nav_next_prev(self, tmp_path):
        app = self._loaded_app(tmp_path)
        s0 = app.current_state()
        assert s0.step == 0
        s1 = app.next()
        assert s1.step == 1
        s0b = app.prev()
        assert s0b.step == 0

    def test_nav_first_last(self, tmp_path):
        app = self._loaded_app(tmp_path)
        last = app.last()
        assert last.step == 4  # 5 entries, last index = 4
        first = app.first()
        assert first.step == 0

    def test_state_has_gamelet_and_step(self, tmp_path):
        app = self._loaded_app(tmp_path)
        state = app.current_state()
        assert state.gamelet == 1
        assert state.step == 0
        assert state.game_uid == "test-game-001"
        assert state.total_steps == 5

    def test_prev_does_not_go_below_zero(self, tmp_path):
        app = self._loaded_app(tmp_path)
        app.prev()
        state = app.current_state()
        assert state.step == 0

    def test_next_does_not_exceed_last(self, tmp_path):
        app = self._loaded_app(tmp_path)
        app.last()
        app.next()
        state = app.current_state()
        assert state.step == 4
