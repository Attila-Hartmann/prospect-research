#!/usr/bin/env python3
"""
Upload prospect JSON to a Google Sheet.
"""

import os
import sys
import json
import argparse
import pandas as pd
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def get_credentials():
    creds = None

    if os.path.exists("token.json"):
        from google.oauth2.credentials import Credentials as UserCredentials
        creds = UserCredentials.from_authorized_user_file("token.json", SCOPES)

    if creds and creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        try:
            creds.refresh(Request())
        except Exception as e:
            print(f"Token refresh failed: {e}", file=sys.stderr)
            creds = None

    if not creds:
        service_account_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
        if os.path.exists(service_account_file):
            with open(service_account_file) as f:
                content = json.load(f)
            if content.get("type") == "service_account":
                print("Using Service Account credentials...")
                creds = Credentials.from_service_account_file(service_account_file, scopes=SCOPES)
            elif "installed" in content:
                print("Using OAuth 2.0 flow...")
                from google_auth_oauthlib.flow import InstalledAppFlow
                flow = InstalledAppFlow.from_client_secrets_file(service_account_file, SCOPES)
                creds = flow.run_local_server(port=0)
                with open("token.json", "w") as token:
                    token.write(creds.to_json())
            else:
                print("Unknown credential format.", file=sys.stderr)
        else:
            print(f"Credentials file '{service_account_file}' not found.", file=sys.stderr)

    return creds

def col_index_to_letter(n):
    result = ""
    while n >= 0:
        result = chr(n % 26 + 65) + result
        n = n // 26 - 1
    return result

def update_sheet(json_file, sheet_name=None, append=False):
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not data:
        print("No data to upload.")
        return None

    df = pd.json_normalize(data)
    df = df.fillna("")  # replace NaN with empty string — gspread can't serialize NaN
    creds = get_credentials()
    if not creds:
        return None

    client = gspread.authorize(creds)

    try:
        if sheet_name:
            try:
                sh = client.open(sheet_name)
                print(f"Opened existing sheet: {sheet_name}")
            except gspread.SpreadsheetNotFound:
                sh = client.create(sheet_name)
                print(f"Created new sheet: {sheet_name}")
        else:
            sh = client.create(f"Prospects Import — {os.path.basename(json_file)}")
            print(f"Created sheet: {sh.title}")

        ws = sh.get_worksheet(0)

        if append:
            existing = ws.get_all_records()
            if not existing:
                # First run: write header row + data
                all_data = [df.columns.values.tolist()] + df.values.tolist()
                ws.update(values=all_data, value_input_option="RAW")
                print(f"First run: wrote headers + {len(df)} rows")
            else:
                existing_ids = {str(r.get("place_id", "")) for r in existing if r.get("place_id")}
                new_df = df[~df["place_id"].astype(str).isin(existing_ids)]
                if new_df.empty:
                    print("All businesses already in sheet — nothing new to add.")
                else:
                    next_row = len(existing) + 2  # +1 for header row, +1 for 1-based index
                    new_data = new_df.values.tolist()
                    end_col = col_index_to_letter(len(new_df.columns) - 1)
                    ws.update(
                        values=new_data,
                        range_name=f"A{next_row}:{end_col}{next_row + len(new_data) - 1}",
                        value_input_option="RAW",
                    )
                    print(f"Appended {len(new_df)} new rows (skipped {len(df) - len(new_df)} duplicates)")
        else:
            ws.clear()

            all_data = [df.columns.values.tolist()] + df.values.tolist()
            req_rows, req_cols = len(all_data), len(df.columns)

            if req_rows > ws.row_count or req_cols > ws.col_count:
                ws.resize(rows=max(req_rows, ws.row_count), cols=max(req_cols, ws.col_count))

            end_col = col_index_to_letter(req_cols - 1)

            if len(all_data) > 1000:
                print(f"Large dataset ({len(all_data)} rows) — using batch upload...")
                for i in range(0, len(all_data), 1000):
                    chunk = all_data[i:i + 1000]
                    start = i + 1
                    end = start + len(chunk) - 1
                    ws.update(values=chunk, range_name=f"A{start}:{end_col}{end}", value_input_option="RAW")
                    print(f"  Rows {start}–{end}")
            else:
                ws.update(values=all_data, value_input_option="RAW")

        user_email = os.getenv("USER_EMAIL")
        if user_email:
            sh.share(user_email, perm_type="user", role="writer")
            print(f"Shared with {user_email}")

        return sh.url

    except Exception as e:
        print(f"Sheet error: {e}", file=sys.stderr)
        return None

def main():
    parser = argparse.ArgumentParser(description="Upload prospects JSON to Google Sheets")
    parser.add_argument("json_file", help="Path to scored JSON file")
    parser.add_argument("--sheet_name", help="Google Sheet name (optional)")
    parser.add_argument("--append", action="store_true",
        help="Append new rows to existing sheet instead of overwriting; deduplicates by place_id")
    args = parser.parse_args()

    url = update_sheet(args.json_file, args.sheet_name, append=args.append)
    if url:
        print(f"Success! Sheet URL: {url}")
    else:
        print("Upload failed.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
