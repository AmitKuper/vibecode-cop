#!/usr/bin/env python3
"""Set up Gmail OAuth 2.0 credentials for game reporting.

Usage:
    python scripts/setup_gmail_oauth.py

This script will:
1. Check for credentials.json in secrets/gmail/
2. Open browser for OAuth authorization
3. Save token.json for future use
4. Verify Gmail API access

No command-line arguments needed.

This file is the entry point and public FACADE; the implementation lives in the
``gmail_oauth_setup`` package (one step per function, <=150 lines per module).
"""

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
for _p in (str(_SCRIPTS_DIR.parent), str(_SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from gmail_oauth_setup.steps import (
    CREDENTIALS_FILE,
    SCOPES,
    TOKEN_FILE,
    authorize,
    check_credentials_file,
    save_token,
    show_next_steps,
    verify_setup,
)

__all__ = [
    "CREDENTIALS_FILE",
    "SCOPES",
    "TOKEN_FILE",
    "authorize",
    "check_credentials_file",
    "main",
    "save_token",
    "show_next_steps",
    "verify_setup",
]


def main():
    """Main setup flow."""
    print("\n" + "=" * 70)
    print("Gmail OAuth 2.0 Setup for Cop-Thief Game Reporting")
    print("=" * 70)

    # Check credentials.json
    if not check_credentials_file():
        sys.exit(1)

    # Run authorization
    creds = authorize()
    if not creds:
        sys.exit(1)

    # Save token
    save_token(creds)

    # Verify
    if not verify_setup():
        print("\n✗ Verification failed")
        sys.exit(1)

    print("\n✓ All checks passed!")

    # Show next steps
    show_next_steps()


if __name__ == "__main__":
    main()
