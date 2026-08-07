"""Write per-gamelet declaration JSON files."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def write_gamelet_declaration(
    game_uid: str,
    sub_game_number: int,
    role: str,
    terms: dict,
    output_dir: str | Path = ".",
) -> Path:
    """Write declaration_g{NN}.json for one gamelet.

    Args:
        game_uid: Canonical series identity.
        sub_game_number: Sub-game index 1..6.
        role: This worker's role.
        terms: Agreed terms dict.
        output_dir: Directory to write the declaration file.

    Returns:
        Path to the written declaration file.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    filename = f"declaration_g{sub_game_number:02d}.json"
    declaration = {
        "game_uid": game_uid,
        "sub_game_number": sub_game_number,
        "role": role,
        "terms": terms,
    }
    path = out / filename
    path.write_text(json.dumps(declaration, indent=2))
    logger.info("Wrote %s", path)
    return path
