"""Send a test email to verify Gmail OAuth token is working.

Usage:
    python scripts/test_gmail.py [recipient]

Default recipient: agentsorch@gmail.com
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

TOKEN_PATH = Path("secrets/gmail/token.json")
DEFAULT_RECIPIENT = "agentsorch@gmail.com"


def main():
    recipient = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RECIPIENT

    if not TOKEN_PATH.exists():
        print(f"ERROR: token not found at {TOKEN_PATH}")
        print("Run: python scripts/gmail_auth.py")
        sys.exit(1)

    print(f"Loading token from {TOKEN_PATH}...")
    from agent.reports.gmail_send import load_oauth_credentials

    try:
        creds = load_oauth_credentials(TOKEN_PATH)
    except Exception as exc:
        print(f"ERROR: token load/refresh failed: {exc}")
        print("Run: python scripts/gmail_auth.py")
        sys.exit(1)

    print(f"Sending test email to {recipient}...")
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    from agent.reports.gmail_send import gmail_api_send

    msg = MIMEMultipart()
    msg["Subject"] = "Hello World — Gmail test from cop-thief agent"
    msg["From"] = "me"
    msg["To"] = recipient
    msg.attach(MIMEText("Hello World!\n\nGmail OAuth token is working correctly.", "plain"))

    try:
        message_id = gmail_api_send(msg, creds)
        print(f"SUCCESS: email sent, message_id={message_id}")
    except Exception as exc:
        print(f"ERROR: send failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
