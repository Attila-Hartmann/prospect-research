#!/usr/bin/env python3
"""
ONE-TIME LOCAL helper (run on a machine with a browser) to mint a Gmail OAuth
refresh token for outreach_publish.py.

The cloud routine cannot do the interactive consent, so we do it once here and
store the resulting refresh token (base64 of the output file) in the routine.

Prereq: a Desktop-app OAuth client downloaded from Google Cloud Console
(project prospect-research-494812), with the Gmail API enabled and the consent
screen set to "In production" (so the refresh token does not expire).

Usage:
    pip install google-auth-oauthlib
    python mint_gmail_token.py --client_secret client_secret.json --output gmail_oauth.json

Opens a browser, asks you to grant the gmail.compose scope to
hartmann.attila88@gmail.com, then writes gmail_oauth.json:
    {client_id, client_secret, refresh_token, token_uri}
"""

import json
import argparse

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


def main():
    ap = argparse.ArgumentParser(description="Mint a Gmail OAuth refresh token")
    ap.add_argument("--client_secret", required=True, help="Desktop-app client_secret JSON")
    ap.add_argument("--output", default="gmail_oauth.json")
    args = ap.parse_args()

    flow = InstalledAppFlow.from_client_secrets_file(args.client_secret, SCOPES)
    # access_type=offline + prompt=consent guarantee a refresh_token is returned.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    if not creds.refresh_token:
        raise SystemExit("No refresh_token returned — re-run (revoke prior grant first).")

    out = {
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {args.output} for {creds.client_id[:24]}…")
    print("Next: base64-encode this file into the routine's GMAIL_OAUTH_B64 secret.")


if __name__ == "__main__":
    main()
