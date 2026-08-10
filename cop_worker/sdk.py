"""CopThiefSDK — the single programmatic entry point to this repository.

``play_match`` / ``play_selftest`` / ``evaluate`` compose the canonical CLIs in a
separate OS process (crash isolation + clean per-match log — docs/DESIGN.md AD-1);
``load_champion`` / ``send_report`` / ``gateway`` are direct in-process calls.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class MatchOutcome:
    """What a finished match process left behind."""

    exit_code: int
    log_path: Path | None
    result_path: Path | None


class CopThiefSDK:
    """Facade over the match runner, evaluation harness, policies, and reporting."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.root = Path(repo_root) if repo_root else REPO_ROOT

    def load_champion(self, role: str):
        """The manifest-selected, checksum-verified counted policy for ``role``."""
        from cop_worker.rl.counted_policy import load_counted_policy

        manifest = (
            self.root / "models" / "MANIFEST.json"
            if role == "cop"
            else self.root.parent / "vibecode-thief" / "models" / "MANIFEST.json"
        )
        return load_counted_policy(manifest, role)

    def _run(self, args: list[str]) -> MatchOutcome:
        proc = subprocess.run(
            [sys.executable, str(self.root / "scripts" / "live_match_ref3.py"), *args],
            cwd=self.root,
            check=False,
        )
        logs = sorted((self.root / "reports" / "ref3_matches").glob("match_*.log"))
        result = self.root / "reports" / "ref3_matches" / "last_match_result.json"
        return MatchOutcome(
            exit_code=proc.returncode,
            log_path=logs[-1] if logs else None,
            result_path=result if result.is_file() else None,
        )

    def play_match(
        self,
        config_profile: str,
        *,
        counted: bool = False,
        counted_played: int | None = None,
        report_to: str | None = None,
        no_email: bool = False,
    ) -> MatchOutcome:
        """Play a live series against the profile's configured opponent."""
        args = ["--match", "--config", config_profile]
        if counted:
            args.append("--counted")
        if counted_played is not None:
            args += ["--counted-played", str(counted_played)]
        if report_to:
            args += ["--report-to", report_to]
        if no_email:
            args.append("--no-email")
        return self._run(args)

    def play_selftest(
        self,
        *,
        role: str = "thief",
        sub_games: int = 2,
        scent_model: str = "subtractive_chebyshev_v1",
        move_policy: str = "hybrid_search",
    ) -> MatchOutcome:
        """Rehearse the full wire against the bundled league-kit sparring peer."""
        return self._run(
            [
                "--self-test",
                "--role",
                role,
                "--sub-games",
                str(sub_games),
                "--scent-model",
                scent_model,
                "--move-policy",
                move_policy,
            ]
        )

    def evaluate(
        self,
        role: str,
        *,
        candidates: str = "",
        scent: str = "chebyshev",
        games: int = 30,
        seed: int = 20260810,
    ) -> int:
        """Run the honest fixed-start harness; returns the process exit code."""
        proc = subprocess.run(
            [
                sys.executable,
                str(self.root / "scripts" / "eval_candidate.py"),
                "--role",
                role,
                "--scent",
                scent,
                "--games",
                str(games),
                "--seed",
                str(seed),
                *(["--candidates", candidates] if candidates else []),
            ],
            cwd=self.root,
            check=False,
        )
        return proc.returncode

    def send_report(self, *, recipient: str, result_path: Path | None = None) -> str:
        """Email a settled result (body + identical attachment); returns the message id."""
        path = result_path or next(iter(sorted(self.root.glob("results/result_*.json"))), None)
        if path is None:
            raise FileNotFoundError("no settled result artifact under results/")
        sys.path.insert(0, str(self.root / "scripts"))
        from ref3_artifacts import email_result  # noqa: PLC0415

        result_obj = json.loads(Path(path).read_text(encoding="utf-8"))
        token = self.root / "secrets" / "gmail" / "token.json"
        return email_result(result_obj, recipient, Path(path).name, token)

    @property
    def gateway(self):
        """The process-wide outbound gateway (rate pacing + retries)."""
        from cop_worker.net_gateway import GATEWAY

        return GATEWAY
