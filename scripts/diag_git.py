#!/usr/bin/env python3
"""Diagnostic: can the cloud sandbox clone + push to GitHub now (post App-install)?
Tests both the plain-URL (managed proxy) and embedded-PAT paths for the pages repo,
plus a non-destructive `git push --dry-run`. Self-reports into a Gmail draft.
(That this script runs at all means the prospect-research clone already succeeded.)"""
import os, sys, re, subprocess, tempfile
sys.path.insert(0, os.path.dirname(__file__))
from email.message import EmailMessage
import outreach_publish as op

PAGES = os.environ.get("PAGES_REPO_URL", "")
PLAIN = re.sub(r"https://[^@/]*@", "https://", PAGES)  # strip embedded credentials


def run(cmd, cwd=None):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120, cwd=cwd)
        out = (p.stdout or "").strip()[-400:]
        err = (p.stderr or "").strip()[-900:]
        return f"$ {cmd}\n[exit {p.returncode}] {out} {err}\n\n"
    except Exception as e:
        return f"$ {cmd}\n[EXC] {type(e).__name__}: {e}\n\n"


base = tempfile.mkdtemp()
log = "=== GIT DIAG (prospect-research clone already succeeded, since this script ran) ===\n\n"
log += "--- A) clone PAGES repo via PLAIN url (managed proxy path) ---\n"
log += run(f'git clone --depth 1 "{PLAIN}" plainclone', cwd=base)
log += "--- B) clone PAGES repo via embedded-PAT url (direct) ---\n"
log += run(f'git clone --depth 1 "{PAGES}" patclone', cwd=base)
for d in ("plainclone", "patclone"):
    p = os.path.join(base, d)
    if os.path.isdir(p):
        run("git config user.email t@t.t", cwd=p)
        run("git config user.name t", cwd=p)
        run("git commit --allow-empty -m diagtest", cwd=p)
        log += f"--- push --dry-run from {d} (NON-destructive) ---\n"
        log += run("git push --dry-run origin HEAD", cwd=p)

print(log)
try:
    msg = EmailMessage()
    msg["From"] = op.SENDER
    msg["To"] = os.getenv("GMAIL_ADDRESS", "")
    msg["Subject"] = "[DIAG] git test"
    msg.set_content(log)
    op.create_draft(msg, op.gmail_access_token())
    print("[diag] wrote Gmail draft: [DIAG] git test")
except Exception as e:
    print(f"[diag] could not write Gmail draft: {type(e).__name__}: {e}")
