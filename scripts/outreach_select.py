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
import datetime

import gspread

# Reuse the exact credential resolution used by update_sheet.py (service account
# or OAuth token), so outreach authenticates the same way as discovery.
from update_sheet import get_credentials, col_index_to_letter
import discover_contact

ELIGIBLE_WEBSITE_TYPES = {"social_only", "none"}
# has_website: the enrichment step found the business already has a live site, so it
# is not a "you have no website" prospect and must never be re-selected.
ALREADY_HANDLED_STATUSES = {"drafted", "sent", "no_email", "skip", "has_website"}

# Consumer-facing trades far more often publish a contact e-mail, so they are
# worked first; B2B/professional offices (accountants, lawyers, real-estate)
# rarely do and tend to yield no_email, so they sink to the back of the queue.
HIGH_PRIORITY_KEYWORDS = (
    "étterem", "vendéglő", "pizzéria", "kávézó", "cukrászda", "büfé", "bisztró",
    "fodrász", "szépségszalon", "kozmetik", "körömszalon", "masszázs", "szolárium",
    "fogorvos", "fogászat", "állatorvos", "optika", "gyógyszertár",
)


def industry_priority(industry):
    text = str(industry).lower()
    return 0 if any(k in text for k in HIGH_PRIORITY_KEYWORDS) else 1

# Fields the agent needs to find an email, write the email, and fill the page.
QUEUE_FIELDS = [
    "place_id", "name", "address", "city", "industry",
    "google_rating", "review_count", "phone", "website", "website_type",
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


def _writeback_has_website(ws, has_site, today):
    """Mark rows the enrichment step found to already have a live website, so they
    are not pitched and not re-selected next run."""
    header = ws.row_values(1)
    if "outreach_status" not in header:
        print("  (no outreach_status column yet — skipping has_website write-back)")
        return
    col = {name: header.index(name) + 1 for name in header}
    batch = []
    for item, res in has_site:
        row = item["_row"]

        def cell(field, value):
            if field in col:
                batch.append({"range": f"{col_index_to_letter(col[field] - 1)}{row}",
                              "values": [[value]]})
        cell("outreach_status", "has_website")
        cell("outreach_notes", res.get("notes", "már van weboldala"))
        cell("outreach_date", today)
        cell("email_address", res.get("email", ""))
    if batch:
        ws.batch_update(batch, value_input_option="RAW")
        print(f"  Marked {len(has_site)} row(s) has_website (skipped, won't be re-selected).")


def enrich_and_fill(ws, eligible, limit):
    """Discover each candidate's website/e-mail over HTTPS. Drop businesses that
    already have a live site (write them back as has_website); pre-fill a discovered
    e-mail on the rest. Fills the queue with up to `limit` genuine no-website prospects."""
    queue, has_site = [], []
    scan_budget = min(len(eligible), max(limit * 2, limit + 10))
    today = datetime.date.today().isoformat()
    for item in eligible[:scan_budget]:
        if len(queue) >= limit:
            break
        try:
            res = discover_contact.discover(
                item.get("name", ""), item.get("city", ""), str(item.get("website", "")))
        except Exception as exc:  # discovery must never break selection
            print(f"  discover error for {item.get('name','?')}: {exc}", file=sys.stderr)
            res = {"site": "", "email": "", "email_source": "", "notes": ""}
        if res.get("site"):
            has_site.append((item, res))
            continue
        if res.get("email"):
            item["discovered_email"] = res["email"]
            item["email_source"] = res.get("email_source", "website")
        queue.append(item)
    if has_site:
        _writeback_has_website(ws, has_site, today)
    return queue, has_site, scan_budget


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

    # Email-rich segments first, then oldest first so the backlog drains evenly
    # (missing dates sort last).
    eligible.sort(key=lambda r: (
        industry_priority(r.get("industry", "")),
        str(records[r["_row"] - 2].get("date_added", "")) or "9999",
    ))

    # Enrich over HTTPS: skip businesses that already have a live website, pre-fill a
    # discovered e-mail on the rest, and fill the queue with genuine no-website prospects.
    queue, has_site, scanned = enrich_and_fill(ws, eligible, limit)

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)

    prefilled = sum(1 for q in queue if q.get("discovered_email"))
    print(f"Eligible: {len(eligible)} | scanned: {scanned} | already-has-website (skipped): "
          f"{len(has_site)} | queued: {len(queue)} (cap {limit}); e-mail pre-found on {prefilled}")
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
