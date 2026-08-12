"""Shared, byte-identical primitives of the two human-play CLIs: keypress
capture, screen clearing, scent glyphs, and key→action maps."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ── Cross-platform single-keypress capture ─────────────────────────────────────

if os.name == "nt":
    import msvcrt

    def _get_key() -> str:
        """Return a normalised key name (one blocking read, no Enter needed)."""
        ch = msvcrt.getch()
        if ch in (b"\xe0", b"\x00"):  # arrow / function-key prefix
            ch2 = msvcrt.getch()
            return {b"H": "UP", b"P": "DOWN", b"K": "LEFT", b"M": "RIGHT"}.get(ch2, "")
        if ch == b" ":
            return "SPACE"
        if ch == b"\r":
            return "ENTER"
        if ch == b"\x1b":
            return "ESC"
        try:
            return ch.decode("utf-8").upper()
        except UnicodeDecodeError:
            return ""
else:
    import termios
    import tty

    def _get_key() -> str:  # type: ignore[misc]
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    return {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT"}.get(ch3, "")
                return "ESC"
            if ch == " ":
                return "SPACE"
            if ch == "\r":
                return "ENTER"
            if ch == "\x1b":
                return "ESC"
            return ch.upper()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


# Repo root (the facades' original ``REPO = Path(__file__).resolve().parents[1]``).
REPO = Path(__file__).resolve().parents[2]

# ── Visual constants ──────────────────────────────────────────────────────────

_SCENT_RAMP = " ·░▒▓"  # 5 levels: empty → faint → dense


def _scent_ch(v: float) -> str:
    idx = min(int(v * len(_SCENT_RAMP)), len(_SCENT_RAMP) - 1)
    return _SCENT_RAMP[idx]


def _clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


# ── Human input (keyboard) ────────────────────────────────────────────────────

# Maps raw key name → movement action
_KEY_TO_MOVE = {
    "UP": "N",
    "W": "N",
    "DOWN": "S",
    "S": "S",
    "LEFT": "W",
    "A": "W",
    "RIGHT": "E",
    "D": "E",
    "SPACE": "STAY",
}

# Maps raw key name → barrier-placement action (used in barrier mode)
_KEY_TO_PLACE = {
    "UP": "PLACE_N",
    "W": "PLACE_N",
    "DOWN": "PLACE_S",
    "S": "PLACE_S",
    "LEFT": "PLACE_W",
    "A": "PLACE_W",
    "RIGHT": "PLACE_E",
    "D": "PLACE_E",
}

_CONTROLS_COP_BARRIER = "  [BARRIER MODE] ↑W↓S←A→D=place direction   Esc=cancel"
