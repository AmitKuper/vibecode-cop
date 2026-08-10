"""CopThiefSDK — the facade must compose the canonical commands, not reinvent them."""

from __future__ import annotations

from pathlib import Path

import pytest

from cop_worker.sdk import CopThiefSDK, MatchOutcome


class TestSdkCommandComposition:
    def _capture(self, monkeypatch):
        calls: list[list[str]] = []

        class _Proc:
            returncode = 0

        def fake_run(cmd, **kwargs):
            calls.append([str(c) for c in cmd])
            return _Proc()

        monkeypatch.setattr("subprocess.run", fake_run)
        return calls

    def test_play_match_composes_the_counted_command(self, monkeypatch) -> None:
        calls = self._capture(monkeypatch)
        sdk = CopThiefSDK()
        outcome = sdk.play_match(
            "imreeyal", counted=True, counted_played=2, report_to="league@example.com"
        )
        assert isinstance(outcome, MatchOutcome)
        cmd = calls[0]
        assert cmd[1].endswith("live_match_ref3.py")
        for part in (
            "--match",
            "--config",
            "imreeyal",
            "--counted",
            "--counted-played",
            "2",
            "--report-to",
            "league@example.com",
        ):
            assert part in cmd

    def test_play_selftest_defaults_to_the_rehearsal_config(self, monkeypatch) -> None:
        calls = self._capture(monkeypatch)
        CopThiefSDK().play_selftest()
        cmd = calls[0]
        for part in ("--self-test", "subtractive_chebyshev_v1", "hybrid_search"):
            assert part in cmd

    def test_no_email_flag_passes_through(self, monkeypatch) -> None:
        calls = self._capture(monkeypatch)
        CopThiefSDK().play_match("imreeyal", no_email=True)
        assert "--no-email" in calls[0]

    def test_evaluate_composes_the_harness_command(self, monkeypatch) -> None:
        calls = self._capture(monkeypatch)
        code = CopThiefSDK().evaluate("cop", candidates="a.pt,b.pt", scent="chebyshev")
        assert code == 0
        cmd = calls[0]
        assert cmd[1].endswith("eval_candidate.py")
        for part in ("--role", "cop", "--scent", "chebyshev", "--candidates", "a.pt,b.pt"):
            assert part in cmd


class TestSdkInProcessSeams:
    def test_load_champion_routes_to_the_manifest_loader(self, monkeypatch) -> None:
        seen = {}

        def fake_load(manifest, role):
            seen["manifest"], seen["role"] = Path(manifest), role
            return object()

        monkeypatch.setattr("cop_worker.rl.counted_policy.load_counted_policy", fake_load)
        CopThiefSDK().load_champion("cop")
        assert seen["role"] == "cop" and seen["manifest"].name == "MANIFEST.json"

    def test_send_report_requires_a_settled_result(self, tmp_path) -> None:
        sdk = CopThiefSDK(repo_root=tmp_path)  # empty tree: no results/
        with pytest.raises(FileNotFoundError, match="no settled result"):
            sdk.send_report(recipient="x@example.com")

    def test_gateway_is_the_process_wide_instance(self) -> None:
        from cop_worker.net_gateway import GATEWAY

        assert CopThiefSDK().gateway is GATEWAY
