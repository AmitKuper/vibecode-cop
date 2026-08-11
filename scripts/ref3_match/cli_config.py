"""CLI argument resolution: config profile + runtime.toml fills (CLI always wins)."""

from __future__ import annotations


def _resolve_args(args) -> None:
    """Fill any unset args from the selected config profile's runtime.toml, in place."""
    from cop_worker.config_loader import load_config
    from ref3_match.runtime_cfg import apply_runtime_config

    cfg = load_config(args.config)
    rt = cfg["runtime"]
    apply_runtime_config(rt)
    net, ident, rep = rt.get("network", {}), rt.get("identity", {}), rt.get("report", {})
    if args.opp_cop_url is None:
        args.opp_cop_url = net.get("opp_cop_url")
    if args.opp_thief_url is None:
        args.opp_thief_url = net.get("opp_thief_url")
    if args.opponent_group is None:
        args.opponent_group = net.get("opponent_group", "anrbj666")
    if args.our_cop_port is None:
        args.our_cop_port = int(net.get("our_cop_port", 61224))
    if args.our_thief_port is None:
        args.our_thief_port = int(net.get("our_thief_port", 61223))
    if args.setting is None:
        args.setting = cfg["game"].get("world", {}).get("map_area", "New York")
    if args.report_to is None:
        args.report_to = rep.get("recipient", "agentsorch@gmail.com")
    if args.members is None:
        args.members = ",".join(ident.get("members", ["Ron Marom", "Amit Kuperminz"]))
    if args.counted_played is None:
        args.counted_played = int(rt.get("counted", {}).get("counted_played", 0))
    if args.scent_model is None:
        args.scent_model = rt.get("protocol", {}).get("scent_model", "multiplicative_book_v1")
    if args.move_policy is None:
        args.move_policy = rt.get("protocol", {}).get("move_policy", "rl")
    # One switch, everywhere: the locked model drives our wire emission (RLMover), our
    # Step-0 declaration (build_negotiation), the peer-frame diagnostic, AND any policy/
    # obs-mode code that reads COPTHIEF_SCENT_MODEL — set the env before policies load.
    import os as _os

    _os.environ["COPTHIEF_SCENT_MODEL"] = args.scent_model
    print(
        f"[match] config profile: {cfg['source']} ({cfg['profile_dir']}) "
        f"scent_model={args.scent_model}"
    )
