"""Tests for reports/gmail_send.py.

Split from test_uncovered_modules_coverage.py; no LLM, no network.
"""


class TestGmailSend:
    def test_load_oauth_credentials_valid_token(self, tmp_path):
        """Test load_oauth_credentials with a mocked valid token file."""
        import json
        from unittest.mock import MagicMock, patch

        token_file = tmp_path / "token.json"
        token_data = {
            "token": "ya29.valid_token",
            "refresh_token": None,
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client_id",
            "client_secret": "client_secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.send"],
        }
        token_file.write_text(json.dumps(token_data))

        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.expiry = "2030-01-01"
        mock_creds.refresh_token = None

        with (
            patch("google.oauth2.credentials.Credentials", return_value=mock_creds),
            patch("google.auth.transport.requests.Request"),
        ):
            from league_manager.reports.gmail_send import load_oauth_credentials

            result = load_oauth_credentials(token_file)
            assert result is mock_creds

    def test_load_oauth_credentials_refreshes_token(self, tmp_path):
        """Test that expired token with refresh_token triggers refresh."""
        import json
        from unittest.mock import MagicMock, patch

        token_file = tmp_path / "token.json"
        token_data = {
            "token": "expired_token",
            "refresh_token": "1//refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client_id",
            "client_secret": "secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.send"],
        }
        token_file.write_text(json.dumps(token_data))

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expiry = None
        mock_creds.refresh_token = "1//refresh_token"
        mock_creds.token = "new_token"
        mock_creds.token_uri = "https://oauth2.googleapis.com/token"
        mock_creds.client_id = "client_id"
        mock_creds.client_secret = "secret"
        mock_creds.scopes = ["https://www.googleapis.com/auth/gmail.send"]

        mock_request_cls = MagicMock()

        with (
            patch("google.oauth2.credentials.Credentials", return_value=mock_creds),
            patch("google.auth.transport.requests.Request", mock_request_cls),
        ):
            from league_manager.reports.gmail_send import load_oauth_credentials

            result = load_oauth_credentials(token_file)
            mock_creds.refresh.assert_called_once()
            assert result is mock_creds

    def test_load_oauth_credentials_raises_without_refresh(self, tmp_path):
        """Invalid token with no refresh_token raises RuntimeError."""
        import json
        from unittest.mock import MagicMock, patch

        import pytest

        token_file = tmp_path / "token.json"
        token_data = {
            "token": None,
            "refresh_token": None,
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client_id",
            "client_secret": "secret",
            "scopes": [],
        }
        token_file.write_text(json.dumps(token_data))

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expiry = None
        mock_creds.refresh_token = None

        with (
            patch("google.oauth2.credentials.Credentials", return_value=mock_creds),
            patch("google.auth.transport.requests.Request"),
        ):
            from league_manager.reports.gmail_send import load_oauth_credentials

            with pytest.raises(RuntimeError, match="re-authorize"):
                load_oauth_credentials(token_file)

    def test_gmail_api_send_returns_message_id(self):
        """Test gmail_api_send with fully mocked API client."""
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from unittest.mock import MagicMock, patch

        message = MIMEMultipart()
        message["Subject"] = "Test"
        message["From"] = "test@test.com"
        message["To"] = "recipient@test.com"
        message.attach(MIMEText("body", "plain"))

        mock_service = MagicMock()
        mock_service.users().messages().send().execute.return_value = {"id": "msg_123"}

        mock_creds = MagicMock()

        with patch("googleapiclient.discovery.build", return_value=mock_service):
            from league_manager.reports.gmail_send import gmail_api_send

            msg_id = gmail_api_send(message, mock_creds)
            assert msg_id == "msg_123"

    def test_gmail_api_send_no_id_returns_unknown(self):
        """Test gmail_api_send when response has no 'id' key."""
        from email.mime.multipart import MIMEMultipart
        from unittest.mock import MagicMock, patch

        message = MIMEMultipart()
        message["Subject"] = "Test"
        message["From"] = "a@b.com"
        message["To"] = "c@d.com"

        mock_service = MagicMock()
        mock_service.users().messages().send().execute.return_value = {}

        with patch("googleapiclient.discovery.build", return_value=mock_service):
            from league_manager.reports.gmail_send import gmail_api_send

            msg_id = gmail_api_send(message, MagicMock())
            assert msg_id == "unknown"
