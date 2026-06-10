#!/usr/bin/env python3
"""
Run this once on your local machine to get YouTube OAuth credentials.
Prints the JSON you need to paste into the YOUTUBE_CREDENTIALS_JSON GitHub secret.

Usage:
    pip install google-auth-oauthlib google-api-python-client
    python scripts/setup_youtube_auth.py
"""

import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def main():
    print("Place your client_secrets.json in this directory first.")
    print("Download it from: Google Cloud Console → Credentials → OAuth 2.0 Client IDs\n")

    flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
    creds = flow.run_local_server(port=0)

    output = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
    }

    print("\n=== COPY THIS INTO YOUR GITHUB SECRET 'YOUTUBE_CREDENTIALS_JSON' ===\n")
    print(json.dumps(output, indent=2))
    print("\n=== END ===")


if __name__ == "__main__":
    main()
