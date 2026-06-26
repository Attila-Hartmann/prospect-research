#!/usr/bin/env python3
"""Diagnostic: can the cloud sandbox upload to the public GCS bucket? Self-reports
into a Gmail draft. Needs GCS_BUCKET + GOOGLE_APPLICATION_CREDENTIALS + gmail oauth."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from email.message import EmailMessage
import outreach_publish as op

try:
    url = op.gcs_upload("_cloud_gcs_test",
                        "<!doctype html><html lang='hu'><head><meta charset='utf-8'>"
                        "<title>cloud gcs</title></head><body><h1>cloud GCS upload OK</h1></body></html>")
    log = f"GCS upload from CLOUD: OK\n{url}"
except Exception as e:
    log = f"GCS upload from CLOUD: FAILED\n{type(e).__name__}: {e}"
print(log)
try:
    m = EmailMessage()
    m["From"] = op.SENDER
    m["To"] = os.getenv("GMAIL_ADDRESS", "")
    m["Subject"] = "[DIAG] gcs test"
    m.set_content(log)
    op.create_draft(m, op.gmail_access_token())
    print("[diag] wrote Gmail draft: [DIAG] gcs test")
except Exception as e:
    print(f"[diag] draft write failed: {type(e).__name__}: {e}")
