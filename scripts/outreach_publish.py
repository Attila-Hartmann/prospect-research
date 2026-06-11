#!/usr/bin/env python3
"""
Publish sample pages, create Gmail drafts (or send), and write outreach status
back to the Google Sheet.

Inputs: .tmp/prepared/<place_id>/{email.json[, index.html]} produced by the agent.

For each prepared business:
  - no email_address  -> mark row `no_email`, skip (no page, no draft).
  - email_address set -> publish index.html to the GitHub Pages repo, build the
    final e-mail (insert sample link + append the standard footer), then:
        SEND_MODE=draft -> IMAP APPEND to the Gmail Drafts folder (review & send by hand)
        SEND_MODE=auto  -> SMTP send
    Recipient is TEST_RECIPIENT when set (safety override), else email_address.
    Drafts/sends are capped at DAILY_CAP per run.
  - Always write back: outreach_status, email_address, email_source,
    sample_page_url, outreach_date, outreach_notes  (matched by place_id).

Env (see .env.example): GMAIL_ADDRESS, GMAIL_APP_PASSWORD, SEND_MODE, TEST_RECIPIENT,
DAILY_CAP, SHEET_NAME, PAGES_REPO_URL, PAGES_BASE_URL, PREPARED_DIR.
"""

import os
import sys
import json
import glob
import time
import smtplib
import imaplib
import subprocess
import datetime
from email.message import EmailMessage
from email.utils import formatdate

from dotenv import load_dotenv
import gspread

from update_sheet import get_credentials, col_index_to_letter

load_dotenv()

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
SEND_MODE = os.getenv("SEND_MODE", "draft").strip().lower()      # draft | auto
TEST_RECIPIENT = os.getenv("TEST_RECIPIENT", "").strip()
DAILY_CAP = int(os.getenv("DAILY_CAP", "25"))
SHEET_NAME = os.getenv("SHEET_NAME", "Hungary Web Prospects")
PAGES_REPO_URL = os.getenv("PAGES_REPO_URL", "")                 # https with token, pushable
PAGES_BASE_URL = os.getenv("PAGES_BASE_URL", "").rstrip("/")     # public github.io base
PREPARED_DIR = os.getenv("PREPARED_DIR", ".tmp/prepared")
PAGES_CLONE = ".tmp/pages_repo"

SENDER = f"Hartmann Attila <{GMAIL_ADDRESS}>"

OUTREACH_COLS = [
    "outreach_status", "email_address", "email_source",
    "sample_page_url", "outreach_date", "outreach_notes",
]

FOOTER = (
    "\n\n—\n"
    "Hartmann Attila · webfejlesztő\n"
    f"✉ {GMAIL_ADDRESS}   ·   Portfólió: https://attila-hartmann.github.io/attila-website/?lang=hu\n"
    "LinkedIn: https://www.linkedin.com/in/attila-hartmann-b7b41a24b/\n\n"
    "Ezt a levelet azért kapta, mert nyilvánosan elérhető céges elérhetőséget találtam Önökhöz. "
    "Ha nem kíván több ilyen levelet kapni, válaszoljon ennyivel: „leiratkozás”, és többé nem írok."
)


# ---------------------------------------------------------------- pages repo ---
def git(*args, cwd=PAGES_CLONE):
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True)


def clone_pages_repo():
    if not PAGES_REPO_URL or not PAGES_BASE_URL:
        print("PAGES_REPO_URL / PAGES_BASE_URL not set — cannot publish pages.", file=sys.stderr)
        sys.exit(1)
    subprocess.run(["rm", "-rf", PAGES_CLONE], check=False)
    subprocess.run(["git", "clone", "--depth", "1", PAGES_REPO_URL, PAGES_CLONE],
                   check=True, capture_output=True, text=True)
    git("config", "user.email", "outreach-agent@attila.web")
    git("config", "user.name", "Attila Outreach Agent")


def stage_page(place_id, index_html_path):
    dest_dir = os.path.join(PAGES_CLONE, place_id)
    os.makedirs(dest_dir, exist_ok=True)
    with open(index_html_path, "r", encoding="utf-8") as src:
        html = src.read()
    with open(os.path.join(dest_dir, "index.html"), "w", encoding="utf-8") as dst:
        dst.write(html)
    return f"{PAGES_BASE_URL}/{place_id}/"


def push_pages(n):
    git("add", "-A")
    status = git("status", "--porcelain").stdout.strip()
    if not status:
        print("No page changes to push.")
        return
    git("commit", "-m", f"outreach: publish {n} sample page(s)")
    git("push", "origin", "HEAD")
    print(f"Pushed {n} sample page(s) to GitHub Pages.")


# -------------------------------------------------------------------- e-mail ---
def build_message(to_addr, subject, body, sample_url):
    if "{{SAMPLE_PAGE_URL}}" in body:
        body = body.replace("{{SAMPLE_PAGE_URL}}", sample_url)
    else:
        body = body.rstrip() + f"\n\nMintaoldal: {sample_url}"
    body += FOOTER

    msg = EmailMessage()
    msg["From"] = SENDER
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(body)
    return msg


def find_drafts_mailbox(imap):
    """Gmail's Drafts folder name is localized ([Gmail]/Drafts vs /Piszkozatok).
    Locate it by the \\Drafts special-use flag; fall back to the English name."""
    try:
        typ, data = imap.list()
        if typ == "OK":
            for raw in data:
                line = raw.decode(errors="ignore")
                if "\\Drafts" in line:
                    # name is the last quoted token on the line
                    return line.split(' "/" ')[-1].strip().strip('"')
    except Exception as e:
        print(f"  (drafts mailbox lookup failed: {e})", file=sys.stderr)
    return "[Gmail]/Drafts"


def create_draft(msg):
    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    imap.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
    mailbox = find_drafts_mailbox(imap)
    imap.append(mailbox, "\\Draft", imaplib.Time2Internaldate(time.time()),
                msg.as_bytes())
    imap.logout()


def send_now(msg):
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)


# --------------------------------------------------------------------- sheet ---
def open_ws():
    creds = get_credentials()
    if not creds:
        print("No credentials — cannot open sheet.", file=sys.stderr)
        sys.exit(1)
    client = gspread.authorize(creds)
    sh = client.open(SHEET_NAME)
    return sh.get_worksheet(0)


def ensure_columns(ws):
    headers = ws.row_values(1)
    missing = [c for c in OUTREACH_COLS if c not in headers]
    for i, name in enumerate(missing):
        ws.update_cell(1, len(headers) + 1 + i, name)
    if missing:
        headers = ws.row_values(1)
    return {name: idx + 1 for idx, name in enumerate(headers)}  # 1-based col index


def row_map(ws):
    records = ws.get_all_records()
    return {str(r.get("place_id", "")): idx + 2 for idx, r in enumerate(records) if r.get("place_id")}


def writeback(ws, colmap, rowmap, results):
    batch = []
    for r in results:
        row = rowmap.get(str(r["place_id"]))
        if not row:
            print(f"  place_id {r['place_id']} not found in sheet — skipping writeback.")
            continue
        for field in OUTREACH_COLS:
            col = colmap[field]
            letter = col_index_to_letter(col - 1)
            batch.append({"range": f"{letter}{row}", "values": [[r.get(field, "")]]})
    if batch:
        ws.batch_update(batch, value_input_option="RAW")
        print(f"Wrote back {len(results)} rows ({len(batch)} cells).")


# ---------------------------------------------------------------------- main ---
def main():
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print("GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set.", file=sys.stderr)
        sys.exit(1)

    today = datetime.date.today().isoformat()
    dirs = sorted(glob.glob(os.path.join(PREPARED_DIR, "*")))
    if not dirs:
        print(f"No prepared businesses in {PREPARED_DIR}.")
        return

    # Split into no-email and sendable.
    sendable, results = [], []
    for d in dirs:
        ejson = os.path.join(d, "email.json")
        if not os.path.isfile(ejson):
            continue
        with open(ejson, encoding="utf-8") as f:
            e = json.load(f)
        pid = str(e.get("place_id", os.path.basename(d)))
        if not e.get("email_address"):
            results.append({
                "place_id": pid, "outreach_status": "no_email",
                "email_address": "", "email_source": e.get("email_source", ""),
                "sample_page_url": "", "outreach_date": today,
                "outreach_notes": e.get("notes", "nem található e-mail cím"),
            })
        else:
            e["_dir"] = d
            e["place_id"] = pid
            sendable.append(e)

    # Publish pages for sendable (up to cap), then draft/send.
    clone_pages_repo()
    capped = sendable[:DAILY_CAP]
    leftover = sendable[DAILY_CAP:]
    if leftover:
        print(f"{len(leftover)} sendable beyond DAILY_CAP={DAILY_CAP} left for a later run.")

    staged = 0
    for e in capped:
        page = os.path.join(e["_dir"], "index.html")
        if not os.path.isfile(page):
            e["_skip"] = "missing index.html"
            continue
        e["_url"] = stage_page(e["place_id"], page)
        staged += 1
    if staged:
        push_pages(staged)

    for e in capped:
        if e.get("_skip"):
            results.append({
                "place_id": e["place_id"], "outreach_status": "skip",
                "email_address": e["email_address"], "email_source": e.get("email_source", ""),
                "sample_page_url": "", "outreach_date": today,
                "outreach_notes": e["_skip"],
            })
            continue

        recipient = TEST_RECIPIENT or e["email_address"]
        subject = e["subject"]
        if TEST_RECIPIENT:
            subject = f"[TESZT → {e['email_address']}] {subject}"
        msg = build_message(recipient, subject, e["body"], e["_url"])

        try:
            if SEND_MODE == "auto":
                send_now(msg)
                status, verb = "sent", "Sent"
            else:
                create_draft(msg)
                status, verb = "drafted", "Drafted"
            print(f"  {verb}: {e['email_address']}  → {recipient}  ({e['_url']})")
            note = e.get("notes", "")
            if TEST_RECIPIENT:
                note = (note + " | TESZT küldés").strip(" |")
        except Exception as exc:
            status = "skip"
            note = f"küldés/draft hiba: {exc}"
            print(f"  ERROR for {e['email_address']}: {exc}", file=sys.stderr)

        results.append({
            "place_id": e["place_id"], "outreach_status": status,
            "email_address": e["email_address"], "email_source": e.get("email_source", ""),
            "sample_page_url": e["_url"], "outreach_date": today,
            "outreach_notes": note,
        })

    # Single batched write-back.
    ws = open_ws()
    colmap = ensure_columns(ws)
    rowmap = row_map(ws)
    writeback(ws, colmap, rowmap, results)

    drafted = sum(1 for r in results if r["outreach_status"] in ("drafted", "sent"))
    no_email = sum(1 for r in results if r["outreach_status"] == "no_email")
    skipped = sum(1 for r in results if r["outreach_status"] == "skip")
    print(f"\nDone. mode={SEND_MODE} cap={DAILY_CAP} "
          f"| {drafted} {'sent' if SEND_MODE=='auto' else 'drafted'}, "
          f"{no_email} no_email, {skipped} skipped.")


if __name__ == "__main__":
    main()
