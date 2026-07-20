"""Gmail OAuth credential management and Gmail API send helper."""

import json
import logging
from base64 import urlsafe_b64encode
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_oauth_credentials(token_path: Path) -> Any:
    """Load and optionally refresh Gmail OAuth credentials from a token file.

    Args:
        token_path: Path to the stored OAuth token JSON file

    Returns:
        Valid ``google.oauth2.credentials.Credentials`` object

    Raises:
        RuntimeError: If token is invalid and cannot be refreshed
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    with open(token_path) as fh:
        token_data = json.load(fh)

    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=token_data.get("scopes"),
    )

    if creds.refresh_token and (not creds.valid or creds.expiry is None):
        logger.info("Refreshing Gmail OAuth token...")
        creds.refresh(Request())
        with open(token_path, "w") as fh:
            json.dump(
                {
                    "token": creds.token,
                    "refresh_token": creds.refresh_token,
                    "token_uri": creds.token_uri,
                    "client_id": creds.client_id,
                    "client_secret": creds.client_secret,
                    "scopes": list(creds.scopes or []),
                },
                fh,
                indent=2,
            )
    elif not creds.valid and not creds.refresh_token:
        raise RuntimeError(
            "Gmail token invalid and no refresh_token"
            " — re-authorize with scripts/gmail_auth.py"
        )

    return creds


def gmail_api_send(message: MIMEMultipart, credentials: Any) -> str:
    """Send a MIME message via the Gmail API.

    Args:
        message: Fully composed MIMEMultipart message
        credentials: Valid OAuth credentials object

    Returns:
        Gmail message ID of the sent message
    """
    from googleapiclient.discovery import build

    service = build("gmail", "v1", credentials=credentials)
    raw = urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    result = (
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
    )
    return result.get("id", "unknown")
