#!/usr/bin/env python3
"""Diagnostic: does the domain-availability path work in THIS environment (cloud)?
Tests raw RDAP + DoH reachability, then the actual module functions. Read-only."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import requests


def t(label, fn):
    s = time.time()
    try:
        print(f"{label}: {fn()!r}  ({time.time() - s:.1f}s)")
    except Exception as e:
        print(f"{label}: ERROR {type(e).__name__}: {e}  ({time.time() - s:.1f}s)")


print("=== raw reachability (no module) ===")
t("RDAP google.com -> status", lambda: requests.get(
    "https://rdap.verisign.com/com/v1/domain/google.com", timeout=10).status_code)
t("RDAP zzqxk-attilatest-9f3a.com -> status", lambda: requests.get(
    "https://rdap.verisign.com/com/v1/domain/zzqxk-attilatest-9f3a.com", timeout=10).status_code)
t("DoH telekom.hu -> Status", lambda: requests.get(
    "https://dns.google/resolve", params={"name": "telekom.hu", "type": "NS"}, timeout=10).json().get("Status"))
t("DoH zzqxk-attilatest-9f3a.hu -> Status", lambda: requests.get(
    "https://dns.google/resolve", params={"name": "zzqxk-attilatest-9f3a.hu", "type": "NS"}, timeout=10).json().get("Status"))

print("\n=== via outreach_publish (the real code path) ===")
try:
    import outreach_publish as op
    print("import outreach_publish: OK")
    t("domain_is_free google.com", lambda: op.domain_is_free("google.com"))
    t("domain_is_free zzqxk-attilatest-9f3a.com", lambda: op.domain_is_free("zzqxk-attilatest-9f3a.com"))
    t("domain_is_free telekom.hu", lambda: op.domain_is_free("telekom.hu"))
    t("domain_is_free zzqxk-attilatest-9f3a.hu", lambda: op.domain_is_free("zzqxk-attilatest-9f3a.hu"))
    t("_derive_stems(White Rose Beauty Salon, Budapest)",
      lambda: op._derive_stems("White Rose Beauty Salon", "Budapest"))
    t("select_free_domains([whiterosebeautysalon, whiterosebeauty, whiterose])",
      lambda: op.select_free_domains(["whiterosebeautysalon", "whiterosebeauty", "whiterose"]))
except Exception as e:
    print(f"import/run outreach_publish FAILED: {type(e).__name__}: {e}")

print("\n=== done ===")
