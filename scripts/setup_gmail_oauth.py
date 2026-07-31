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
"""

import json
import sys
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print(
        "ERROR: google-auth-oauthlib not installed.\n"
        "Install with: pip install google-auth-oauthlib\n"
    )
    sys.exit(1)


SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CREDENTIALS_FILE = Path("secrets/gmail/credentials.json")
TOKEN_FILE = Path("secrets/gmail/token.json")


def check_credentials_file():
    """Verify credentials.json exists."""
    if not CREDENTIALS_FILE.exists():
        print("ERROR: credentials.json not found")
        print(f"Expected at: {CREDENTIALS_FILE.absolute()}\n")
        print("Steps to fix:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a new project (or use existing)")
        print("3. Enable Gmail API")
        print("4. Create OAuth 2.0 Desktop App credentials")
        print("5. Download credentials.json to secrets/gmail/")
        print("\nSee agent/docs/GMAIL_SETUP.md for detailed instructions")
        return False

    print(f"✓ Found credentials.json at {CREDENTIALS_FILE.absolute()}")
    return True


def authorize():
    """Run OAuth 2.0 authorization flow."""
    print("\nStarting Gmail OAuth authorization...")
    print("A browser window will open. Sign in and grant permission.\n")

    try:
        # Create flow from credentials.json
        flow = InstalledAppFlow.from_client_secrets_file(
            CREDENTIALS_FILE,
            SCOPES,
        )

        # Run local server for OAuth callback
        creds = flow.run_local_server(port=8080, open_browser=True)

        print("\n✓ Authorization successful")
        return creds

    except Exception as e:
        print(f"\n✗ Authorization failed: {e}")
        return None


def save_token(creds):
    """Save credentials to token.json."""
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": SCOPES,
        "type": "authorized_user",
    }

    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    # Set restrictive permissions (Unix-like systems only; Windows has no chmod)
    import contextlib
    with contextlib.suppress(Exception):
        TOKEN_FILE.chmod(0o600)

    print(f"✓ Saved token.json at {TOKEN_FILE.absolute()}")


def verify_setup():
    """Verify Gmail OAuth is ready."""
    print("\nVerifying setup...")

    checks = [
        ("credentials.json exists", CREDENTIALS_FILE.exists()),
        ("token.json exists", TOKEN_FILE.exists()),
    ]

    all_ok = True
    for check_name, result in checks:
        status = "✓" if result else "✗"
        print(f"  {status} {check_name}")
        if not result:
            all_ok = False

    return all_ok


def show_next_steps():
    """Show user what to do next."""
    print("\n" + "=" * 70)
    print("Gmail OAuth Setup Complete!")
    print("=" * 70)
    print("\nNext steps:")
    print("1. Verify config files have correct settings:")
    print("   - cop/config.toml:   [reports.gmail] mode='send'")
    print("   - thief/config.toml: [reports.gmail] mode='send'")
    print("   - recipient: agentsorch@gmail.com")
    print("\n2. Start agents:")
    print("   Terminal 1: python -m cop")
    print("   Terminal 2: python -m thief")
    print("\n3. Run a game:")
    print("   Terminal 3: python short_game.py")
    print("\n4. Check Gmail inbox (agentsorch@gmail.com)")
    print("   Should receive game report with attachments")
    print("\nSee agent/docs/GMAIL_SETUP.md for full details")
    print("=" * 70)


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
