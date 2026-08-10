"""The canonical protocol spec and placeholder examples fed to the planner."""

from __future__ import annotations

_CANONICAL_PROTOCOL_SPEC = """
Canonical CopThief MCP Protocol — local specification

REQUIRED PHASES:
  start_game  — begin a gamelet; fields: game_id, gamelet, role, config_sha256, timestamp
  commit      — commit to a move; fields: game_id, step, role, commitment
                (H(move||nonce||game_id...)), config_sha256, timestamp, hint (optional)
  reveal      — reveal move; fields: game_id, step, role, move (N/S/E/W/STAY or PLACE_*),
                nonce (only at final_audit), config_sha256, timestamp
  final_audit — bilateral audit; fields: game_id, step, role, nonces (dict step→nonce),
                config_sha256, timestamp
  audit_summary — signed comprehensive audit summary; fields: game_id, role,
                signed_audit_summary
  game_end — independently checked gamelet outcome; fields: game_id, step, role, reason
  result_agreement — signed result; fields: game_id, role, result_hash, signed_agreement
  abort — controlled technical-loss/abort; fields: game_id, step, role, reason

PROTECTED FIELDS (must not be mutated by mapping):
  game_id, gamelet, step, role, commitment, signature, config_sha256, nonces,
  signed_audit_summary, signed_agreement

BINDING RULES:
  - nonce is secret until final_audit
  - commitment = SHA-256(canonical_message_bytes)
  - phase ordering: start_game → (commit → reveal)* → final_audit → game_end;
    after exactly six gamelets → result_agreement
  - no canonicalization change is allowed mid-series
"""

_PLACEHOLDER_EXAMPLES = """
Example commit request (placeholder values — not real):
  {"game_id": "GAME_EXAMPLE_001", "step": 1, "role": "cop",
   "commitment": "abc123def456...", "config_sha256": "sha256placeholder",
   "timestamp": "2026-01-01T00:00:00Z", "hint": "I am heading north."}

Example reveal request:
  {"game_id": "GAME_EXAMPLE_001", "step": 1, "role": "cop",
   "move": "N", "config_sha256": "sha256placeholder",
   "timestamp": "2026-01-01T00:00:00Z"}
"""
