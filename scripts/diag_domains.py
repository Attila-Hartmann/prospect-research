#!/usr/bin/env python3
"""Diagnostic: map the cloud sandbox's network egress + find a working domain-
availability path. Self-reports into a Gmail draft (Gmail API is allowlisted) so the
result is readable without access to the routine session. Read-only otherwise."""
import os
import sys
import time
import socket
from email.message import EmailMessage

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import requests

LINES = []


def log(s):
    print(s)
    LINES.append(s)


def probe(label, fn):
    s = time.time()
    try:
        log(f"{label}: {fn()!r}  ({time.time() - s:.2f}s)")
    except Exception as e:
        log(f"{label}: ERROR {type(e).__name__}: {str(e)[:120]}  ({time.time() - s:.2f}s)")


def http(url, **kw):
    r = requests.get(url, timeout=10, **kw)
    return f"{r.status_code} | {r.text[:50]!r}"


log("=== A) HTTP egress allowlist probe ===")
probe("rdap.verisign.com", lambda: http("https://rdap.verisign.com/com/v1/domain/google.com"))
probe("rdap.org", lambda: http("https://rdap.org/domain/google.com"))
probe("dns.google (DoH)", lambda: http("https://dns.google/resolve?name=telekom.hu&type=NS"))
probe("cloudflare-dns.com (DoH)", lambda: http("https://cloudflare-dns.com/dns-query?name=telekom.hu&type=NS",
                                               headers={"accept": "application/dns-json"}))
probe("r.jina.ai", lambda: http("https://r.jina.ai/https://example.com"))
probe("whoisjson.com", lambda: http("https://whoisjson.com/api/v1/whois?domain=telekom.hu"))
probe("www.googleapis.com", lambda: http("https://www.googleapis.com/discovery/v1/apis"))
probe("pypi.org", lambda: http("https://pypi.org/simple/"))
probe("api.github.com", lambda: http("https://api.github.com"))
probe("attila-hartmann.github.io", lambda: http("https://attila-hartmann.github.io/attila-landing-samples/"))

log("\n=== B) system resolver (socket.getaddrinfo) for arbitrary domains ===")
def gai(host):
    try:
        ips = sorted({r[4][0] for r in socket.getaddrinfo(host, 443, socket.AF_INET)})
        return f"OK {ips[:3]}"
    except Exception as e:
        return f"{type(e).__name__}: {str(e)[:60]}"
probe("getaddrinfo telekom.hu", lambda: gai("telekom.hu"))
probe("getaddrinfo google.com", lambda: gai("google.com"))
probe("getaddrinfo zzqxk-nonexist-9f3a.hu (expect fail if free)", lambda: gai("zzqxk-nonexist-9f3a.hu"))
probe("getaddrinfo zzqxk-nonexist-9f3a.com (expect fail if free)", lambda: gai("zzqxk-nonexist-9f3a.com"))
probe("getaddrinfo kovacsfogaszat.hu", lambda: gai("kovacsfogaszat.hu"))

log("\n=== C) current module path ===")
try:
    import outreach_publish as op
    probe("op.select_free_domains([whiterosebeautysalon,whiterose])",
          lambda: op.select_free_domains(["whiterosebeautysalon", "whiterose"]))
except Exception as e:
    log(f"import outreach_publish FAILED: {type(e).__name__}: {e}")

log("\n=== done ===")

# Self-report into a Gmail draft so the result is retrievable.
try:
    import outreach_publish as op
    msg = EmailMessage()
    msg["From"] = op.SENDER
    msg["To"] = os.getenv("GMAIL_ADDRESS", "")
    msg["Subject"] = "[DIAG] domain egress probe"
    msg.set_content("\n".join(LINES))
    op.create_draft(msg, op.gmail_access_token())
    print("\n[diag] wrote results to a Gmail draft: [DIAG] domain egress probe")
except Exception as e:
    print(f"\n[diag] could not write Gmail draft: {type(e).__name__}: {e}")
