#!/usr/bin/env python3
"""
Select prospects eligible for outreach from the persistent Google Sheet.

Reads the "Hungary Web Prospects" sheet, keeps only grade-A businesses with no
real website that have not been contacted yet, and writes a capped queue to JSON
for the agent to enrich (find email + write copy + build a sample page).

Eligibility:
  - prospect_score == "A"
  - website_type in ("social_only", "none")   # i.e. has_website == false
  - business_status == "OPERATIONAL"
  - outreach_status empty or "queued"          # never re-contact drafted/sent/no_email/skip

Output records are ordered oldest-first (by date_added) so the backlog is worked
down over successive runs, then capped to --limit.
"""

import os
import sys
import json
import argparse

import gspread

# Reuse the exact credential resolution used by update_sheet.py (service account
# or OAuth token), so outreach authenticates the same way as discovery.
from update_sheet import get_credentials

ELIGIBLE_WEBSITE_TYPES = {"social_only", "none"}
ALREADY_HANDLED_STATUSES = {"drafted", "sent", "no_email", "skip"}

# Fields the agent needs to find an email, write the email, and fill the page.
QUEUE_FIELDS = [
    "place_id", "name", "address", "city", "industry",
    "google_rating", "review_count", "phone", "website_type",
    "social_url", "recommended_approach",
]


def is_eligible(row):
    if str(row.get("prospect_score", "")).strip().upper() != "A":
        return False
    if str(row.get("website_type", "")).strip() not in ELIGIBLE_WEBSITE_TYPES:
        return False
    if str(row.get("business_status", "")).strip() != "OPERATIONAL":
        return False
    status = str(row.get("outreach_status", "")).strip().lower()
    if status in ALREADY_HANDLED_STATUSES:
        return False
    return True


def select(sheet_name, output, limit):
    creds = get_credentials()
    if not creds:
        print("No credentials — cannot read sheet.", file=sys.stderr)
        sys.exit(1)

    client = gspread.authorize(creds)
    try:
        sh = client.open(sheet_name)
    except gspread.SpreadsheetNotFound:
        print(f"Sheet '{sheet_name}' not found.", file=sys.stderr)
        sys.exit(1)

    ws = sh.get_worksheet(0)
    records = ws.get_all_records()  # list of dicts keyed by header row

    eligible = []
    for idx, row in enumerate(records):
        if not is_eligible(row):
            continue
        item = {k: row.get(k, "") for k in QUEUE_FIELDS}
        item["_row"] = idx + 2  # 1-based, +1 for header — used for sheet write-back
        eligible.append(item)

    # Oldest first so the backlog drains; missing dates sort last.
    eligible.sort(key=lambda r: str(records[r["_row"] - 2].get("date_added", "")) or "9999")

    queue = eligible[:limit]

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)

    print(f"Eligible: {len(eligible)} | queued this run: {len(queue)} (cap {limit})")
    print(f"Wrote {output}")
    print(f"Sheet URL: {sh.url}")


def main():
    parser = argparse.ArgumentParser(description="Select outreach-eligible prospects from the sheet")
    parser.add_argument("--sheet_name", default="Hungary Web Prospects")
    parser.add_argument("--output", default=".tmp/queue.json")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    select(args.sheet_name, args.output, args.limit)


if __name__ == "__main__":
    main()
