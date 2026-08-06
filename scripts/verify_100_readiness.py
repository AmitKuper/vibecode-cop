#!/usr/bin/env python3
"""Strict executable verifier for all locally code-verifiable release gates.

There is deliberately no option to skip a mandatory gate.  Real-world course
actions are reported as EXTERNAL_PENDING and are never treated as local proof.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

REPO = Path(__file__).resolve().parents[1]
WORKSPACE = REPO.parent
REPOS = {"cop": WORKSPACE / "vibecode-cop", "thief": WORKSPACE / "vibecode-thief"}
REFERENCE_KIT = WORKSPACE / "external" / "copthief-league-protocol"
Status = Literal["PASS", "FAIL", "EXTERNAL_PENDING"]


@dataclass(frozen=True)
class Gate:
    gate_id: str
    description: str
    status: Status
    detail: str
    elapsed_ms: float


def run(command: list[str], cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def tail(result: subprocess.CompletedProcess[str], limit: int = 1200) -> str:
    text = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    return text[-limit:] or f"exit={result.returncode}"


def evaluate(gate_id: str, description: str, check: Callable[[], str]) -> Gate:
    started = time.monotonic()
    try:
        detail = check()
        status: Status = "PASS"
    except Exception as exc:  # every gate must yield a durable result
        detail = f"{type(exc).__name__}: {exc}"
        status = "FAIL"
    elapsed = (time.monotonic() - started) * 1000
    print(f"{gate_id} {status}: {detail}", flush=True)
    return Gate(gate_id, description, status, detail, elapsed)


def require_success(result: subprocess.CompletedProcess[str], label: str) -> None:
    if result.returncode:
        raise RuntimeError(f"{label} failed ({result.returncode}): {tail(result)}")


def git_sha(repo: Path) -> str:
    result = run(["git", "rev-parse", "HEAD"], repo, 30)
    require_success(result, "git rev-parse")
    return result.stdout.strip()


def check_clean() -> str:
    evidence: list[str] = []
    for role, repo in REPOS.items():
        result = run(["git", "status", "--short"], repo, 30)
        require_success(result, f"{role} git status")
        if result.stdout.strip():
            raise RuntimeError(f"{role} worktree is dirty: {result.stdout.strip()}")
        evidence.append(f"{role}={git_sha(repo)}")
    return ", ".join(evidence)


def check_dependencies() -> str:
    evidence: list[str] = []
    for role, repo in REPOS.items():
        sync = run(["uv", "sync", "--frozen"], repo, 900)
        require_success(sync, f"{role} uv sync --frozen")
        lock = run(["uv", "lock", "--check"], repo, 120)
        require_success(lock, f"{role} uv lock --check")
        isolated = run(
            [
                "uv",
                "run",
                "--isolated",
                "python",
                "-c",
                "import numpy, torch; assert torch.__version__ and numpy.__version__",
            ],
            repo,
            900,
        )
        require_success(isolated, f"{role} isolated production dependency import")
        evidence.append(f"{role}=sync+lock+isolated-torch")
    return ", ".join(evidence)


def _coverage_omission_check(repo: Path) -> None:
    config = (repo / "pyproject.toml").read_text(encoding="utf-8")
    forbidden = (
        "agent/adaptive",
        "agent/audit",
        "agent/domain",
        "agent/gmail",
        "agent/peer",
        "agent/reliability",
        "agent/reports/gmail",
        "agent/rl/recurrent",
        "agent/rl/train*.py",
        "agent/rl/strategies*.py",
    )
    present = [item for item in forbidden if item in config]
    if present:
        raise RuntimeError(f"broad mandatory coverage omissions remain: {present}")


def check_tests_and_coverage() -> str:
    evidence: list[str] = []
    with tempfile.TemporaryDirectory(prefix="vibecode-coverage-") as temp:
        temp_path = Path(temp)
        for role, repo in REPOS.items():
            _coverage_omission_check(repo)
            coverage_json = temp_path / f"{role}-coverage.json"
            junit_xml = temp_path / f"{role}-junit.xml"
            result = run(
                [
                    "uv",
                    "run",
                    "python",
                    "-m",
                    "pytest",
                    "-q",
                    "--cov=agent",
                    "--cov-branch",
                    f"--cov-report=json:{coverage_json}",
                    "--cov-report=term",
                    f"--junitxml={junit_xml}",
                ],
                repo,
                1800,
            )
            require_success(result, f"{role} full pytest")
            xml_root = ET.parse(junit_xml).getroot()
            suites = [xml_root] if xml_root.tag == "testsuite" else list(xml_root.iter("testsuite"))
            tests = max((int(s.attrib.get("tests", 0)) for s in suites), default=0)
            skipped = max((int(s.attrib.get("skipped", 0)) for s in suites), default=0)
            failures = max((int(s.attrib.get("failures", 0)) for s in suites), default=0)
            errors = max((int(s.attrib.get("errors", 0)) for s in suites), default=0)
            if tests <= 0 or skipped or failures or errors:
                raise RuntimeError(
                    f"{role} junit tests={tests}, skipped={skipped}, "
                    f"failures={failures}, errors={errors}"
                )
            totals = json.loads(coverage_json.read_text(encoding="utf-8"))["totals"]
            covered = int(totals["covered_branches"])
            total = int(totals["num_branches"])
            percent = (100.0 * covered / total) if total else 0.0
            if total <= 0 or percent < 85.0:
                raise RuntimeError(f"{role} branch coverage {covered}/{total}={percent:.4f}%")
            evidence.append(
                f"{role}={tests} tests, 0 skipped, branches {covered}/{total}={percent:.4f}%"
            )
    return "; ".join(evidence)


def check_ruff() -> str:
    for role, repo in REPOS.items():
        lint = run(["uv", "run", "ruff", "check", "."], repo, 300)
        require_success(lint, f"{role} Ruff lint")
        formatting = run(["uv", "run", "ruff", "format", "--check", "."], repo, 300)
        require_success(formatting, f"{role} Ruff format")
    return "both repositories: zero lint violations and formatting clean"


def check_cli_startup() -> str:
    for role, repo in REPOS.items():
        result = run(["uv", "run", "python", "-m", role, "--help"], repo, 120)
        require_success(result, f"{role} CLI startup")
        if "counted" not in result.stdout or "serve" not in result.stdout:
            raise RuntimeError(f"{role} help omits counted/serve production commands")
    return "cop and thief package CLIs start cleanly and expose counted serving"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_models() -> str:
    evidence: list[str] = []
    config_hashes: set[str] = set()
    for role, repo in REPOS.items():
        manifest_path = repo / "models" / "MANIFEST.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        matches = [entry for entry in manifest["models"] if entry["role"] == role]
        if len(matches) != 1:
            raise RuntimeError(f"{role} manifest role entry count={len(matches)}")
        entry = matches[0]
        artifact = manifest_path.parent / entry["artifact"]
        actual = sha256(artifact)
        if actual != entry["sha256"] or entry["algorithm"] != "RecurrentA2C-GRU":
            raise RuntimeError(f"{role} artifact/manifest mismatch")
        if int(entry.get("training_steps", 0)) <= 0:
            raise RuntimeError(f"{role} manifest has no training evidence")
        config_hashes.add(entry["config_sha256"])
        code = (
            "from agent.rl.recurrent_policy import load_recurrent_policy; "
            f"p=load_recurrent_policy(r'{manifest_path}', r'{role}'); "
            "assert p.network.training is False"
        )
        loaded = run(["uv", "run", "--isolated", "python", "-c", code], repo, 900)
        require_success(loaded, f"{role} checksum/inference load")
        evidence.append(f"{role}={actual}")
    if len(config_hashes) != 1:
        raise RuntimeError(f"champions bind different configs: {sorted(config_hashes)}")
    return "; ".join(evidence)


def _stable_tournament_payload(data: dict) -> dict:
    """Return only deterministic competitive evidence for exact rerun comparison."""
    baseline = dict(data["strongest_heuristic_baseline"])
    baseline.pop("average_inference_and_environment_ms", None)
    baseline.pop("inference_latency_ms", None)
    return {
        key: data[key]
        for key in (
            "role",
            "held_out_series",
            "held_out_games",
            "wins",
            "win_rate",
            "confidence_95",
            "series_wins",
            "series_win_rate",
            "series_confidence_95",
            "official_role_score",
            "official_opponent_score",
            "worst_family_win_rate",
            "worst_family_series_win_rate",
            "average_turns",
            "technical_failures",
            "illegal_action_rate",
            "action_correction_rate",
            "inference_mode",
            "inference_temperature",
            "families",
            "promotion_gate",
        )
    } | {"strongest_heuristic_baseline": baseline}


def check_tournaments() -> str:
    evidence: list[str] = []
    with tempfile.TemporaryDirectory(prefix="vibecode-tournament-") as temp:
        for role, repo in REPOS.items():
            path = repo / "results" / f"{role}_held_out_tournament.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            required = (
                "held_out_games",
                "held_out_series",
                "win_rate",
                "confidence_95",
                "worst_family_win_rate",
                "inference_latency_ms",
                "technical_failures",
                "official_role_score",
                "official_opponent_score",
                "promotion_gate",
                "evaluation_seed",
            )
            missing = [key for key in required if key not in data]
            if missing:
                raise RuntimeError(f"{role} tournament missing {missing}")
            if data.get("role") != role or int(data["held_out_games"]) != 6 * int(
                data["held_out_series"]
            ):
                raise RuntimeError(f"{role} tournament is not paired six-gamelet evidence")
            if len(data.get("families", {})) < 4 or int(data["technical_failures"]) != 0:
                raise RuntimeError(f"{role} tournament lacks diverse zero-failure families")
            if not data["promotion_gate"].get("passed"):
                raise RuntimeError(f"{role} champion did not pass paired promotion")
            manifest = json.loads((repo / "models" / "MANIFEST.json").read_text(encoding="utf-8"))
            artifact_entry = next(entry for entry in manifest["models"] if entry["role"] == role)
            if data.get("artifact_sha256") != artifact_entry["sha256"]:
                raise RuntimeError(f"{role} tournament targets a different artifact")

            output_dir = Path(temp) / role
            opponent_role = "thief" if role == "cop" else "cop"
            command = [
                "uv",
                "run",
                "python",
                "-m",
                "agent.rl.train_recurrent",
                "--role",
                role,
                "--eval-series-per-family",
                str(int(data["held_out_series"]) // len(data["families"])),
                "--seed",
                str(int(data["evaluation_seed"])),
                "--historical-checkpoint",
                str(repo / "models" / f"{opponent_role}_ppo_best.pt"),
                "--evaluate-only-artifact",
                str(repo / "models" / artifact_entry["artifact"]),
                "--evidence-dir",
                str(output_dir),
            ]
            if data.get("inference_temperature") is not None:
                command.extend(["--inference-temperature", str(data["inference_temperature"])])
            rerun = run(command, repo, 1200)
            require_success(rerun, f"{role} exact held-out tournament rerun")
            reproduced = json.loads(
                (output_dir / f"{role}_held_out_tournament.json").read_text(encoding="utf-8")
            )
            stable_expected = _stable_tournament_payload(data)
            stable_actual = _stable_tournament_payload(reproduced)
            if stable_actual != stable_expected:
                raise RuntimeError(f"{role} tournament rerun does not reproduce frozen evidence")
            stable_hash = hashlib.sha256(
                json.dumps(stable_actual, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            evidence.append(
                f"{role}={data['held_out_series']} series/{data['held_out_games']} games, "
                f"win={100 * float(data['win_rate']):.2f}%, "
                f"worst={100 * float(data['worst_family_win_rate']):.2f}%, "
                f"reproduced={stable_hash}"
            )
    return "; ".join(evidence)


def check_strategy_analysis() -> str:
    evidence: list[str] = []
    required_common = {
        "full_release",
        "strongest_heuristic",
        "scent_only_no_belief",
        "belief_only_no_scent",
        "stateless",
        "no_legal_mask",
        "language_off",
    }
    for role, repo in REPOS.items():
        manifest = json.loads((repo / "models" / "MANIFEST.json").read_text(encoding="utf-8"))
        entry = next(item for item in manifest["models"] if item["role"] == role)
        analysis = json.loads(
            (repo / "results" / "rl" / "strategy_analysis.json").read_text(encoding="utf-8")
        )
        if analysis.get("artifact_sha256") != entry["sha256"]:
            raise RuntimeError(f"{role} strategy analysis targets stale model")
        if int(analysis.get("series_per_family", 0)) < 5:
            raise RuntimeError(f"{role} strategy analysis sample is too small")
        rows = {row["variant"]: row for row in analysis.get("ablations", [])}
        required = required_common | {"no_barrier_actions" if role == "cop" else "belief_risk_mask"}
        if not required.issubset(rows):
            raise RuntimeError(f"{role} strategy analysis missing {sorted(required - rows.keys())}")
        full = rows["full_release"]
        if (
            int(full["gamelets"]) != 300
            or int(full["technical_failures"]) != 0
            or float(full["illegal_action_rate"]) != 0.0
        ):
            raise RuntimeError(f"{role} full-release ablation is not clean executable evidence")
        if float(rows["no_legal_mask"]["illegal_action_rate"]) <= 0.0:
            raise RuntimeError(f"{role} legal-mask ablation did not exercise illegal selection")
        if analysis.get("language_official_score_delta") != 0:
            raise RuntimeError(f"{role} movement/language separation is not invariant")
        if len(analysis.get("sensitivity", [])) < 4:
            raise RuntimeError(f"{role} deterministic/stochastic sensitivity is incomplete")

        curriculum = json.loads(
            (repo / "results" / "rl" / "curriculum_comparison.json").read_text(encoding="utf-8")
        )
        comparison = curriculum["single_checkpoint_self_play"]
        comparison_path = repo / "results" / "rl" / comparison["artifact"]
        if sha256(comparison_path) != comparison["artifact_sha256"]:
            raise RuntimeError(f"{role} single-opponent comparison checksum mismatch")
        if (
            curriculum.get("status") != "PASS"
            or float(curriculum.get("population_score_differential_advantage", 0)) <= 0
        ):
            raise RuntimeError(f"{role} population curriculum comparison did not pass")

        curves = (repo / "results" / "rl" / "learning_curves.csv").read_text(encoding="utf-8")
        if entry["sha256"] not in curves or "true" not in curves.lower():
            raise RuntimeError(f"{role} learning curve does not end at release artifact")
        card = (repo / "docs" / "RL_MODEL_CARD.md").read_text(encoding="utf-8")
        tournament = (repo / "docs" / "RL_TOURNAMENT_REPORT.md").read_text(encoding="utf-8")
        if entry["sha256"] not in card or entry["sha256"] not in tournament:
            raise RuntimeError(f"{role} model documentation is not release-checksum bound")
        if "PLACEHOLDER" in card or "EXTERNAL_PENDING" not in card:
            raise RuntimeError(f"{role} model card has stale or dishonest readiness status")
        evidence.append(
            f"{role}=release {100 * float(full['win_rate']):.2f}%, "
            f"{len(rows)} ablations, {len(analysis['sensitivity'])} sensitivity points"
        )
    return "; ".join(evidence)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def check_reference_v3_interop() -> str:
    if not REFERENCE_KIT.is_dir():
        raise RuntimeError(f"untouched reference-v3 clone missing: {REFERENCE_KIT}")
    before = run(["git", "status", "--short"], REFERENCE_KIT, 30)
    require_success(before, "reference-v3 git status")
    if before.stdout.strip():
        raise RuntimeError(f"reference-v3 clone is dirty: {before.stdout.strip()}")
    reference_sha = git_sha(REFERENCE_KIT)
    vectors = run(["uv", "run", "python", "verify_vectors.py"], REFERENCE_KIT, 180)
    require_success(vectors, "reference-v3 published vectors")
    if "113 checks" not in vectors.stdout or "ALL VECTORS PASS" not in vectors.stdout:
        raise RuntimeError(f"reference-v3 vector total not proven: {tail(vectors)}")

    profiles: set[str] = set()
    for role, repo in REPOS.items():
        command = [
            "uv",
            "run",
            "python",
            "scripts/verify_reference_v3_interop.py",
            "--kit-root",
            str(REFERENCE_KIT),
            "--external-port",
            str(_free_port()),
            "--local-port",
            str(_free_port()),
        ]
        result = run(command, repo, 300)
        require_success(result, f"{role} bidirectional reference-v3 interop")
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        payload = json.loads("\n".join(lines[lines.index("{") :])) if "{" in lines else None
        if not isinstance(payload, dict) or payload.get("status") != "PASS":
            raise RuntimeError(f"{role} invalid reference-v3 evidence: {tail(result)}")
        if payload.get("external_sha") != reference_sha:
            raise RuntimeError(f"{role} reference-v3 SHA drift")
        client_evidence = payload.get("our_client_to_external_server", {})
        if int(client_evidence.get("per_turn_llm_calls", -1)) != 0:
            raise RuntimeError(f"{role} reference-v3 path uses a per-turn protocol LLM")
        profiles.add(str(client_evidence.get("profile_hash")))

    after = run(["git", "status", "--short"], REFERENCE_KIT, 30)
    require_success(after, "reference-v3 final git status")
    if after.stdout.strip():
        raise RuntimeError("reference-v3 verifier modified the external clone")
    if len(profiles) != 1:
        raise RuntimeError(f"role adapters disagree on reference-v3 profile: {profiles}")
    return f"reference={reference_sha}, vectors=113/113, profile={next(iter(profiles))}"


FOCUSED_TESTS = (
    "tests/test_codex_adaptive_transport.py",
    "tests/test_codex_adaptive_contract_coverage.py",
    "tests/test_adaptive_discovery_hardening.py",
    "tests/test_codex_counted_composition.py",
    "tests/test_codex_bilateral_result.py",
    "tests/test_codex_game_end_consensus.py",
    "tests/test_audit_adversarial.py",
    "tests/test_replay_audit.py",
    "tests/test_watchdog.py",
    "tests/test_codex_pipeline_gmail_contract.py",
    "tests/test_codex_process_gmail.py",
    "tests/test_codex_recurrent_failure_contract.py",
    "tests/test_codex_recurrent_training.py",
    "tests/test_codex_token_accounting.py",
    "tests/test_codex_real_adaptive_fixture_matrix_v11.py",
    "tests/test_codex_reference_v3_interop.py",
    "tests/test_codex_competitive_strategy_v11.py",
)


def check_hostile_suites() -> str:
    evidence: list[str] = []
    for role, repo in REPOS.items():
        absent = [path for path in FOCUSED_TESTS if not (repo / path).is_file()]
        if absent:
            raise RuntimeError(f"{role} missing mandatory hostile suites: {absent}")
        result = run(["uv", "run", "python", "-m", "pytest", "-q", *FOCUSED_TESTS], repo, 600)
        require_success(result, f"{role} hostile/recovery/Gmail suites")
        if " skipped" in result.stdout:
            raise RuntimeError(f"{role} focused suite skipped tests: {tail(result)}")
        evidence.append(f"{role}={result.stdout.strip().splitlines()[-1]}")
    return "; ".join(evidence)


def check_two_process() -> str:
    verifier = REPOS["cop"] / "scripts" / "verify_local_two_process.py"
    with tempfile.TemporaryDirectory(prefix="vibecode-two-process-") as temp:
        result = run(
            [
                "uv",
                "run",
                "python",
                str(verifier),
                "--output-dir",
                temp,
            ],
            REPOS["cop"],
            900,
        )
        require_success(result, "real two-process six-gamelet acceptance")
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        payload = json.loads(lines[-1])
        if payload.get("status") != "PASS" or payload.get("gamelets") != 6:
            raise RuntimeError(f"invalid two-process evidence: {payload}")
        return (
            f"series={payload['series_id']}, gamelets=6, agreement={payload['agreement_hash']}, "
            f"ledger_consensus={payload['ledger_consensus_sha256']}"
        )


SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"sk-[A-Za-z0-9]{32,}"),
    re.compile(r"ya29\.[0-9A-Za-z_-]{20,}"),
)


def check_secrets() -> str:
    findings: list[str] = []
    for role, repo in REPOS.items():
        listed = run(["git", "ls-files", "-z"], repo, 60)
        require_success(listed, f"{role} tracked file listing")
        for relative in listed.stdout.split("\0"):
            if not relative:
                continue
            path = repo / relative
            if not path.is_file() or path.stat().st_size > 5_000_000:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if any(pattern.search(content) for pattern in SECRET_PATTERNS):
                findings.append(f"{role}:{relative}")
    if findings:
        raise RuntimeError(f"credential-like tracked content: {findings}")
    return "tracked-file credential pattern scan clean in both repositories"


def check_documents() -> str:
    required = (
        "README.md",
        "PRD.md",
        "PLAN.md",
        "TODO.md",
        "FINAL_100_READINESS_REPORT.md",
        "FINAL_EXTERNAL_ACTION_CHECKLIST.md",
        "FINAL_RELEASE_MANIFEST.json",
        "results/score_100_verification.json",
        "docs/CODEX_100_READINESS_EXECPLAN.md",
        "docs/PROGRAM_EXECUTION_LEDGER.md",
        "docs/REQUIREMENTS_TRACEABILITY.md",
    )
    stale_claims = (
        "14/14 PASS",
        "2 skipped",
        "placeholder weights",
        "PPO model weights",
        "script not yet implemented",
        "TOURNAMENT_EXTERNAL_PENDING",
    )
    for role, repo in REPOS.items():
        missing = [relative for relative in required if not (repo / relative).is_file()]
        if missing:
            raise RuntimeError(f"{role} missing documents: {missing}")
        readme = (repo / "README.md").read_text(encoding="utf-8")
        if "recurrent champion" not in readme.lower() or "EXTERNAL_PENDING" not in readme:
            raise RuntimeError(f"{role} README does not describe current policy/external boundary")
        final_report = (repo / "FINAL_100_READINESS_REPORT.md").read_text(encoding="utf-8")
        if any(claim in final_report for claim in stale_claims):
            raise RuntimeError(f"{role} final report retains obsolete readiness claims")
        reproduction = (repo / "docs" / "RL_REPRODUCTION.md").read_text(encoding="utf-8")
        if "agent.rl.train_recurrent" not in reproduction or any(
            claim in reproduction for claim in stale_claims
        ):
            raise RuntimeError(f"{role} RL reproduction guide is stale")
        matrix = (repo / "docs" / "REQUIREMENTS_TRACEABILITY.md").read_text(encoding="utf-8")
        rows = re.findall(r"^\|\s*(\d+)\.", matrix, flags=re.MULTILINE)
        if sorted(map(int, rows)) != list(range(1, 56)):
            raise RuntimeError(f"{role} traceability matrix is not exactly 55 rules")
        json.loads((repo / "FINAL_RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    return (
        "required artifacts present, current README claims, exact 55-rule matrices, valid manifests"
    )


def external_gate(gate_id: str, description: str, detail: str) -> Gate:
    gate = Gate(gate_id, description, "EXTERNAL_PENDING", detail, 0.0)
    print(f"{gate_id} EXTERNAL_PENDING: {detail}", flush=True)
    return gate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="write the verification report to this path")
    args = parser.parse_args()

    checks = (
        ("CV-01", "Clean exact repository revisions", check_clean),
        ("CV-02", "Frozen dependencies and lock consistency", check_dependencies),
        ("CV-03", "Full suites, zero skips, branch coverage >=85%", check_tests_and_coverage),
        ("CV-04", "Ruff lint and format", check_ruff),
        ("CV-05", "Clean subprocess CLI startup", check_cli_startup),
        ("CV-06", "Champion checksum, schema, and inference load", check_models),
        ("CV-07", "Held-out six-gamelet tournament promotion", check_tournaments),
        ("CV-07A", "Exact-checkpoint analysis and documentation", check_strategy_analysis),
        (
            "CV-08",
            "Adaptive/tamper/replay/Watchdog/Gmail/token hostile suites",
            check_hostile_suites,
        ),
        ("CV-09", "Real isolated two-process six-gamelet production path", check_two_process),
        (
            "CV-09A",
            "Untouched published reference-v3 bidirectional interoperability",
            check_reference_v3_interop,
        ),
        ("CV-10", "Tracked secret scan", check_secrets),
        ("CV-11", "Documentation claim and 55-rule validation", check_documents),
    )
    gates = [evaluate(*check) for check in checks]
    gates.extend(
        (
            external_gate(
                "EXT-01",
                "Public tunnel and outside-opponent matches",
                "Requires a genuine public endpoint and other course groups; "
                "no evidence fabricated.",
            ),
            external_gate(
                "EXT-02",
                "Independent real Gmail delivery",
                "Requires real OAuth credentials and returned Gmail message IDs; "
                "fake acceptance mail is local proof only.",
            ),
            external_gate(
                "EXT-03",
                "Real group identity and Moodle submissions",
                "Requires the actual eight-character group ID, official PDF layout, "
                "screenshots, and individual human submissions.",
            ),
            external_gate(
                "EXT-04",
                "Final documented tag pushed to remotes",
                "Creating/pushing the audited release tag is an external repository action.",
            ),
        )
    )
    counts = {
        status: sum(g.status == status for g in gates)
        for status in ("PASS", "FAIL", "EXTERNAL_PENDING")
    }
    code_pass = all(g.status == "PASS" for g in gates if g.gate_id.startswith("CV-"))
    report = {
        "schema_version": "2.0",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "repository_shas": {role: git_sha(repo) for role, repo in REPOS.items()},
        "summary": counts,
        "all_code_verifiable_pass": code_pass,
        "code_verifiable_score": 100 if code_pass else None,
        "submission_ready": code_pass and counts["EXTERNAL_PENDING"] == 0,
        "gates": [asdict(gate) for gate in gates],
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if code_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
