"""Step-zero identity + refusal diagnostics (split from subgame_setup)."""

from __future__ import annotations

from league_artifacts.declaration import _hardware_spec, counted_opponents

from ref3_match.runtime_cfg import REPO_ROOT, _git_head


def build_identity(role: str, group_id: str, group_name: str, members, our_counted: int) -> dict:
    """Our step-zero identity on the wire (rules 49/53): repos, per-role
    github_commit, counted count, members — so the peer records what we
    actually declare."""
    from ref3_artifacts import OUR_REPOS, our_mcp

    our_repo = REPO_ROOT if role == "police" else REPO_ROOT.parent / "vibecode-thief"
    return {
        "group_id": group_id,
        "group_name": group_name,
        # Honest declaration: the verbal layer is template-generated (no language model is
        # called during play, so no LLM tokens are consumed). Movement is deliberately
        # described only as algorithmic Python — the book requires declaring the LLM, not
        # the movement strategy, and hints provably cannot affect ours (local_obs_to_tensor
        # never reads last_hint).
        "llm_model": "none (template hints; pure-Python algorithmic movement)",
        "mcp_servers": our_mcp(),
        "repos": OUR_REPOS,
        "members": members or [],
        "github_commit": _git_head(our_repo),
        "hardware_spec": _hardware_spec(),
        "counted_games_played": our_counted,
        # Both spellings, same integer, plus the list rule 38 consistency-checks against.
        "counted_matches_played": our_counted,
        "opponents_already_counted": counted_opponents(),
    }


def print_refusal_diag(sub_game: int, greeting: dict, theirs: dict, exc: Exception) -> None:
    """A refusal is only actionable if it names the DIFF, not just the rule."""
    t_terms = theirs.get("terms") if isinstance(theirs.get("terms"), dict) else {}
    ours_terms = greeting["terms"]
    key_diff = sorted(set(ours_terms) ^ set(t_terms))
    val_diff = {
        k: (ours_terms.get(k), t_terms.get(k))
        for k in ours_terms
        if k in t_terms and ours_terms[k] != t_terms[k]
    }
    print(f"[match] sg{sub_game} HANDSHAKE REFUSED: {exc}")
    print(f"[diag ] terms key diff (ours^theirs): {key_diff or 'none'}")
    print(f"[diag ] terms value diff (ours vs theirs): {val_diff or 'none'}")
    print(
        f"[diag ] locks ours scent={greeting.get('scent_model_sha256', '')[:12]} "
        f"wire={greeting.get('wire_shape_sha256', '')[:12]} | theirs "
        f"scent={str(theirs.get('scent_model_sha256'))[:12]} "
        f"wire={str(theirs.get('wire_shape_sha256'))[:12]}"
    )
    print(
        f"[diag ] uid ours={greeting.get('game_uid')} theirs={theirs.get('game_uid')} "
        f"role ours={greeting.get('role')} theirs={theirs.get('role')} "
        f"sub_game ours={sub_game} theirs={theirs.get('sub_game_number')}"
    )
