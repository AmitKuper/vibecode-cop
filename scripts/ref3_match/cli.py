"""Argument parsing and dispatch: --self-test vs --match."""

from __future__ import annotations

import argparse
import asyncio
import json as _json
from pathlib import Path

from ref3_match.artifacts_io import _write_result
from ref3_match.cli_config import _resolve_args
from ref3_match.ingress_boot import ensure_ingress
from ref3_match.match_log import _install_match_log
from ref3_match.report_guard import _emit_artifacts
from ref3_match.runtime_cfg import KIT_ROOT
from ref3_match.selftest import _self_test
from ref3_match.selftest_split import _self_test_split
from ref3_match.series import _play_match
from ref3_match.series_split import _play_match_split


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Reference-v3 match orchestrator (RL policy moves)")
    p.add_argument("--self-test", action="store_true", help="Play vs the local sparring peer")
    # Process architecture: split = one OS process per role + this orchestrator
    # (Appendix E rules 1-3); inline = the legacy single-process runtime.
    p.add_argument("--arch", choices=["split", "inline"], default="split")
    p.add_argument("--role", choices=["police", "thief"], default="police")
    p.add_argument("--sub-games", type=int, default=1)
    p.add_argument("--our-port", type=int, default=5011)
    p.add_argument("--sparring-port", type=int, default=8941)
    p.add_argument("--kit-root", type=Path, default=KIT_ROOT)
    # Config profile selection: --config <name|dir> picks config/opponents/<name>/ (else base
    # config/). CLI flags below always override the profile's values (defaults are None so we
    # can tell "unset" from an explicit value).
    p.add_argument(
        "--config",
        default=None,
        help="Config profile: a name under config/opponents/, or a directory",
    )
    # Real-match args:
    p.add_argument("--match", action="store_true", help="Play a live peer over reference-v3")
    p.add_argument("--opp-cop-url", help="Opponent cop MCP URL (dialed when we are thief)")
    p.add_argument("--opp-thief-url", help="Opponent thief MCP URL (dialed when we are cop)")
    p.add_argument("--opponent-group", default=None)
    p.add_argument("--our-cop-port", type=int, default=None)
    p.add_argument("--our-thief-port", type=int, default=None)
    p.add_argument("--setting", default=None)
    # Result recipient. Default = OUR OWN inbox (never the league address). The counted/league
    # address is passed explicitly at run time for a counted game only.
    p.add_argument("--report-to", default=None)
    p.add_argument("--no-email", action="store_true", help="Skip emailing the result")
    p.add_argument(
        "--members", default=None, help="Comma-separated member names for the declaration"
    )
    # Counted-game accounting (rules 37-38): friendly = counted=False (no increment).
    p.add_argument("--counted", action="store_true", help="Mark this as a COUNTED series")
    p.add_argument(
        "--counted-played",
        type=int,
        default=None,
        help="Our prior counted-games count (for games_played_including_this)",
    )
    p.add_argument(
        "--scent-model",
        default=None,
        choices=("multiplicative_book_v1", "subtractive_chebyshev_v1"),
        help="Locked scent model for this pairing (default: [protocol] in runtime.toml)",
    )
    p.add_argument(
        "--move-policy",
        default=None,
        choices=("rl", "hybrid_search", "hybrid_search_belief"),
        help="Move engine: plain RL, or minimax-over-exact-tracking with RL fallback",
    )
    return p


def main() -> int:
    args = _build_parser().parse_args()
    _resolve_args(args)

    if args.match:
        if not (args.opp_cop_url and args.opp_thief_url):
            print("ERROR: --match requires --opp-cop-url and --opp-thief-url (CLI or runtime.toml)")
            return 2
        _install_match_log(args.opponent_group or "unknown")
        ensure_ingress()
        members = [m.strip() for m in args.members.split(",") if m.strip()]
        play = _play_match_split if args.arch == "split" else _play_match
        result = asyncio.run(
            play(
                opp_cop_url=args.opp_cop_url,
                opp_thief_url=args.opp_thief_url,
                our_cop_port=args.our_cop_port,
                our_thief_port=args.our_thief_port,
                opponent_group=args.opponent_group,
                setting=args.setting,
                sub_games=args.sub_games if args.sub_games > 1 else 6,
                members=members,
                our_counted=args.counted_played,
                scent_model=args.scent_model,
                move_policy=args.move_policy,
            )
        )
        _write_result(result)  # raw internal snapshot (debug)
        oks = [sg for sg in result["sub_games"] if sg.get("audit_ok")]
        print(f"\n[match] STATUS: audits {len(oks)}/{len(result['sub_games'])} ok")
        _emit_artifacts(result, args)
        return 0 if oks and len(oks) == len(result["sub_games"]) else 1

    if not args.self_test:
        print("Use --self-test (vs sparring) or --match --opp-cop-url ... --opp-thief-url ...")
        return 2
    kit = args.kit_root.resolve()
    if not (kit / "verify_vectors.py").is_file():
        print(f"ERROR: not a league-protocol clone: {kit}")
        return 1
    _install_match_log("selftest")
    self_test = _self_test_split if args.arch == "split" else _self_test
    result = asyncio.run(
        self_test(
            args.role,
            args.sub_games,
            args.our_port,
            args.sparring_port,
            kit,
            scent_model=args.scent_model,
            move_policy=args.move_policy,
        )
    )
    print("\n[match] RESULT:", _json.dumps(result, indent=2))
    oks = [sg for sg in result["sub_games"] if sg.get("audit_ok")]
    sgs = result["sub_games"]
    rl_ok = all(sg.get("distinct_moves", 0) > 1 for sg in sgs) if sgs else False
    print(
        f"[match] STATUS: audits {len(oks)}/{len(result['sub_games'])} ok; RL-varied-moves={rl_ok}"
    )
    return 0 if oks and rl_ok else 1
