# Gmail OAuth 2.0 Setup Guide

## Overview

To enable Gmail reporting, you need OAuth 2.0 credentials. This guide walks through the setup.

**Important:** Never commit `credentials.json` or `token.json` to Git. They are in `.gitignore`.

---

## Prerequisites

- Google account (not Gmail-only — can be any Google account)
- Python 3.13+
- Google Cloud SDK or web console access

---

## Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a Project** → **New Project**
3. Name: `cop-thief-game` (or any name)
4. Click **Create**

---

## Step 2: Enable Gmail API

1. In Google Cloud Console, search for **Gmail API**
2. Click **Enable**
3. You should see: "Gmail API is now enabled"

---

## Step 3: Create OAuth 2.0 Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth 2.0 Client ID**
3. If prompted, configure the OAuth consent screen first:
   - User Type: **External**
   - Fill in:
     - App name: `Cop-Thief Game`
     - User support email: your email
     - Developer contact: your email
   - Scopes: Add `https://www.googleapis.com/auth/gmail.send` (SEND-ONLY scope)
4. Back to Credentials, click **Create Credentials** → **OAuth 2.0 Client ID** again
5. Application type: **Desktop application**
6. Name: `cop-thief-reporter`
7. Click **Create**

---

## Step 4: Download credentials.json

1. In Credentials page, find your new OAuth 2.0 Client ID
2. Click the download icon (down arrow) on the right
3. Save as: `secrets/gmail/credentials.json`

**Directory structure:**
```
project/
├── secrets/
│   └── gmail/
│       └── credentials.json   ← Downloaded from Google Cloud Console
└── cop/config.toml           ← Points to secrets/gmail/credentials.json
```

---

## Step 5: Generate token.json (First Authorization)

Run this Python script **once** to authorize and generate `token.json`:

```python
#!/usr/bin/env python3
"""Generate Gmail OAuth token.json"""

import json
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.service_account import ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CREDENTIALS_FILE = Path("secrets/gmail/credentials.json")
TOKEN_FILE = Path("secrets/gmail/token.json")


def authorize():
    """Run OAuth authorization flow."""
    CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Load credentials.json
    flow = InstalledAppFlow.from_client_secrets_file(
        CREDENTIALS_FILE, SCOPES, redirect_uri="http://localhost:8080"
    )

    # Open browser for user authorization
    creds = flow.run_local_server(port=8080)

    # Save token.json
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": SCOPES,
    }

    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"✓ Token saved to {TOKEN_FILE}")
    print(f"✓ Gmail OAuth is now configured")
    print(f"✓ Set mode='send' in config.toml to enable reporting")


if __name__ == "__main__":
    authorize()
```

**To run:**
```bash
pip install google-auth-oauthlib google-auth-httplib2

python scripts/gmail_auth.py
```

This will:
1. Open a browser window
2. Ask you to sign in to your Google account
3. Ask for permission to send Gmail (SEND-ONLY scope)
4. Create `secrets/gmail/token.json` automatically

---

## Step 6: Verify Setup

After running the authorization script:

```bash
# Check token exists
ls -la secrets/gmail/token.json

# Check config has correct paths
cat cop/config.toml | grep -A 5 "\[reports.gmail\]"
```

Should show:
```
[reports.gmail]
enabled = true
mode = "send"
recipient = "agentsorch@gmail.com"
credentials_path = "secrets/gmail/credentials.json"
token_path = "secrets/gmail/token.json"
```

---

## Step 7: Integration in Orchestrator

The orchestrator's game_end handler should call:

```python
# In agent/orchestrator.py, after game completes:

from agent.reports.bundle import ReportBundleBuilder
from agent.reports.plugin_factory import ReportPluginFactory
from agent.reports.manager import ReportManager


async def handle_game_end(self, game_id: str, game_state: dict):
    """Called when game ends."""

    try:
        # Build report context
        context = await ReportBundleBuilder(self.games_dir / game_id).build(
            game_id=game_id,
            role=self.role,
            game_state=game_state,
            result={"winner": game_state.get("winner")},
            config_hash=self.config_sha256,
            metadata={"group_id": self.group_id},
        )

        # Create plugins from config
        plugins = await ReportPluginFactory.from_config(self.config.get("reports", {}))

        # Generate all reports
        results = await ReportManager(plugins).generate_all(context)

        # Log results
        logger.info(f"Report generation complete: {results}")

    except Exception as e:
        logger.error(f"Report generation failed: {e}", exc_info=True)
        # Don't crash — game is already saved
```

---

## Troubleshooting

### "credentials.json not found"

```
Error: credentials_path = "secrets/gmail/credentials.json" doesn't exist
```

**Fix:** Download credentials.json from Google Cloud Console (Step 4).

### "token.json not found"

```
Error: token_path = "secrets/gmail/token.json" doesn't exist
```

**Fix:** Run Gmail authorization script (Step 5). This opens a browser for OAuth flow.

### "GMAIL API not enabled"

If you get 403 Forbidden from Gmail API:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Search for **Gmail API**
3. Click **Enable**

### "Invalid OAuth scope"

If you see `auth_exception: invalid_grant`:

1. Delete `token.json`
2. Run authorization script again
3. Make sure OAuth consent screen includes `gmail.send` scope

### Test Without Real Credentials

To test without Gmail:

```toml
[reports.gmail]
enabled = true
mode = "dry_run"  # ← Won't need credentials, saves local .txt preview
recipient = "agentsorch@gmail.com"
```

Then switch to `mode = "send"` after verifying credentials work.

---

## Security Notes

✅ **Safe:**
- `credentials.json` (client ID only, no user secrets)
- `token.json` (refresh token, user-specific)
- `secrets/` folder is in `.gitignore`

❌ **Never commit:**
- `credentials.json`
- `token.json`
- Any files in `secrets/`

✅ **Scope is minimal:**
- `gmail.send` only — can only send emails
- No read, delete, or modify access to mailbox

---

## Quick Checklist

- [ ] Created Google Cloud Project
- [ ] Enabled Gmail API
- [ ] Created OAuth 2.0 Desktop App credentials
- [ ] Downloaded `credentials.json` to `secrets/gmail/`
- [ ] Ran authorization script (generated `token.json`)
- [ ] Updated `cop/config.toml` (mode=send, recipient=agentsorch@gmail.com)
- [ ] Updated `thief/config.toml` (mode=send, recipient=agentsorch@gmail.com)
- [ ] Verified `secrets/` is in `.gitignore`
- [ ] Ready to run agents with Gmail reporting enabled

---

## Next Steps

1. Run agents: `python -m cop` and `python -m thief`
2. Start a game: `python short_game.py` or `python start_game.py`
3. Check Gmail inbox: `agentsorch@gmail.com` should receive game reports

Each report email includes:
- Game ID, role, group, result
- Start/end timestamps
- Config hash, log hash
- Attached game files (declaration, config, log, result, report.md)
