"""Detect silent divergence between the cop and thief copies of shared modules.

The repos deliberately duplicate a pinned set of modules (each must clone and
run standalone); the cost is drift - `signing.py` or `networks.py` quietly
differing would make the two agents disagree about the protocol or the
observation layout, failing nothing until a counted match. Any byte-difference
in the pinned set fails; role-specific files are simply not listed.

    python scripts/check_shared_drift.py          # gate (exit 1 on drift)
    python scripts/check_shared_drift.py --list   # show every pinned pair
Skips cleanly (exit 0) when the sibling repo is absent (single-repo clone).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SIBLING = REPO_ROOT.parent / "vibecode-thief"
COP_PKG, THIEF_PKG = "cop_worker", "thief_worker"

#: Module paths (relative to each repo's worker package) that MUST stay identical.
SHARED_WORKER_MODULES = [
    "audit/step_evidence.py",
    "config/shared_config_validate.py",
    "config_loader.py",
    "domain/types_observation.py",
    "gui/app.py",
    "gui/dashboard.py",
    "gui/hub_api.py",
    "gui/hub_page.py",
    "gui/live_view_model.py",
    "gui/page.py",
    "gui/play_page.py",
    "gui/replay_page.py",
    "replay/game_record.py",
    "replay/ref3_steps.py",
    "replay/replay_board.py",
    "domain/types_records.py",
    "gmail/circuit_breaker.py",
    "gmail/dos_detector.py",
    "gmail/token_bucket.py",
    "language/hint_policy.py",
    "language/hints.py",
    "language/llm_prompts.py",
    "llm/config.py",
    "llm/token_counter.py",
    "logging_setup.py",
    "mcp/capability_negotiation.py",
    "mcp/fixture_protocols.py",
    "mcp/transport_port.py",
    "observation.py",
    "observation_processor.py",
    "parameter_registry.py",
    "protocol/conformance_types.py",
    "protocol/introspector_types.py",
    "protocol/mapping_plan.py",
    "protocol/protocol_agent_spec.py",
    "protocol/transport_types.py",
    "protocol/verifier_types.py",
    "reliability/durable_io.py",
    "rl/action_space.py",
    "rl/config.py",
    "rl/networks.py",
    "rules_outcomes.py",
    "scent_chebyshev.py",
    "runtime_mode.py",
    "step0/lifecycle_artifacts.py",
    "step0/signing.py",
    "synthetic_belief.py",
    "version.py",
]

#: Repo-root-relative paths shared verbatim outside the worker packages.
#: NOT listed: tools/submission_builder/builder.py and its helper - the two repos
#: split that module differently (cop: rows.py, thief: ledger.py) and each builds
#: only its own repo's view of the ledger, so byte-identity is not the contract.
SHARED_ROOT_FILES = [
    "tests/test_submission_builder.py",
]


def _sha(path: Path) -> str | None:
    """Hash with the OWN package name normalised away.

    A shared module necessarily imports its own package (`cop_worker.x` vs
    `thief_worker.x`); that difference is the point of duplicating it, not drift.
    Everything else - logic, constants, signatures - must match byte for byte.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    normalised = text.replace(COP_PKG, "<worker>").replace(THIEF_PKG, "<worker>")
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def pairs() -> list[tuple[str, Path, Path]]:
    out = [
        (f"<worker>/{rel}", REPO_ROOT / COP_PKG / rel, SIBLING / THIEF_PKG / rel)
        for rel in SHARED_WORKER_MODULES
    ]
    out += [(rel, REPO_ROOT / rel, SIBLING / rel) for rel in SHARED_ROOT_FILES]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if not SIBLING.is_dir():
        print(f"SKIP  sibling repo not found at {SIBLING} - nothing to compare")
        return 0

    drift, missing, ok = [], [], 0
    for label, a, b in pairs():
        sa, sb = _sha(a), _sha(b)
        if sa is None or sb is None:
            missing.append((label, a if sa is None else b))
        elif sa != sb:
            drift.append((label, sa[:12], sb[:12]))
        else:
            ok += 1
            if args.list:
                print(f"same  {sa[:12]}  {label}")

    for label, path in missing:
        print(f"GONE  {label}: {path} does not exist - update SHARED_* or restore the file")
    for label, sa, sb in drift:
        print(f"DRIFT {label}: cop {sa} != thief {sb}")
    if drift or missing:
        print(f"\n{len(drift)} drifted, {len(missing)} missing.")
        print("Shared modules must stay byte-identical across repos; sync both copies")
        print("or drop the entry with a reason in docs/KNOWN_DEVIATIONS.md.")
        return 1
    print(f"OK  {ok} shared file(s) byte-identical across both repos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
