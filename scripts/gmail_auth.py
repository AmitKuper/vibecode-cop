"""Re-authorize Gmail OAuth token. Run once interactively; opens browser.

Usage:
    python scripts/gmail_auth.py
"""

import json
import sys
from pathlib import Path

CREDENTIALS_PATH = Path("secrets/gmail/credentials.json")
TOKEN_PATH = Path("secrets/gmail/token.json")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
]


def main():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("ERROR: google-auth-oauthlib not installed.")
        print("Run: .venv\\Scripts\\uv.exe pip install google-auth google-auth-oauthlib google-api-python-client")  # noqa: E501
        sys.exit(1)

    if not CREDENTIALS_PATH.exists():
        print(f"ERROR: credentials.json not found at {CREDENTIALS_PATH}")
        sys.exit(1)

    print(f"Starting OAuth flow for Gmail (scopes: {SCOPES})")
    print("A browser window will open. Sign in and authorize the app.")

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
    }

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"\nToken saved to {TOKEN_PATH}")
    print("Gmail authorization complete. You can now run games with mode=send.")


if __name__ == "__main__":
    main()
