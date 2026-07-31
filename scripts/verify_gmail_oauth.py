#!/usr/bin/env python3
"""Verify Gmail OAuth setup is working."""

import json
from pathlib import Path

CREDENTIALS_FILE = Path("secrets/gmail/credentials.json")
TOKEN_FILE = Path("secrets/gmail/token.json")


def verify():
    """Verify Gmail OAuth files are present and valid."""
    print("\nVerifying Gmail OAuth Setup\n" + "=" * 50)

    # Check credentials.json
    if not CREDENTIALS_FILE.exists():
        print(f"[FAIL] credentials.json NOT found at {CREDENTIALS_FILE}")
        return False

    try:
        with open(CREDENTIALS_FILE) as f:
            creds = json.load(f)
        client_id = creds.get("installed", {}).get("client_id", "N/A")[:20]
        print("[OK] credentials.json found")
        print(f"     Client ID: {client_id}...")
    except Exception as e:
        print(f"[FAIL] credentials.json invalid: {e}")
        return False

    # Check token.json
    if not TOKEN_FILE.exists():
        print(f"[FAIL] token.json NOT found at {TOKEN_FILE}")
        return False

    try:
        with open(TOKEN_FILE) as f:
            token = json.load(f)
        token_value = token.get("token", "N/A")[:20]
        refresh_token = token.get("refresh_token", "N/A")[:20]
        print("[OK] token.json found")
        print(f"     Token: {token_value}...")
        print(f"     Refresh: {refresh_token}...")
        print(f"     Scopes: {token.get('scopes', [])}")
    except Exception as e:
        print(f"[FAIL] token.json invalid: {e}")
        return False

    # Check config
    cop_config = Path("cop/config.toml")
    if cop_config.exists():
        content = cop_config.read_text()
        if 'mode = "send"' in content and "agentsorch@gmail.com" in content:
            print("[OK] cop/config.toml configured for send to agentsorch@gmail.com")
        elif 'mode = "send"' in content:
            print("[WARN] cop/config.toml mode=send, but check recipient")
        else:
            print("[WARN] cop/config.toml not set to mode='send'")

    thief_config = Path("thief/config.toml")
    if thief_config.exists():
        content = thief_config.read_text()
        if 'mode = "send"' in content and "agentsorch@gmail.com" in content:
            print("[OK] thief/config.toml configured for send to agentsorch@gmail.com")
        elif 'mode = "send"' in content:
            print("[WARN] thief/config.toml mode=send, but check recipient")
        else:
            print("[WARN] thief/config.toml not set to mode='send'")

    print("\n" + "=" * 50)
    print("[SUCCESS] Gmail OAuth is configured and ready!")
    print("\nNext steps:")
    print("1. Start agents: python -m cop & python -m thief")
    print("2. Run game: python short_game.py")
    print("3. Check email: agentsorch@gmail.com should receive game report")
    print("\nReports will be sent to: agentsorch@gmail.com")
    print("=" * 50 + "\n")

    return True


if __name__ == "__main__":
    import sys
    success = verify()
    sys.exit(0 if success else 1)
