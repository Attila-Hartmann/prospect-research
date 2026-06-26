#!/usr/bin/env python3
"""
Publish sample pages, create Gmail drafts (or send), and write outreach status
back to the Google Sheet.

Inputs: .tmp/prepared/<place_id>/{email.json[, index.html]} produced by the agent.

For each prepared business:
  - no email_address  -> mark row `no_email`, skip (no page, no draft).
  - email_address set -> publish index.html to the GitHub Pages repo, build thef
    final e-mail (insert sample link + append the standard footer), then via the
    Gmail REST API (HTTPS — the cloud sandbox blocks IMAP/SMTP ports):
        SEND_MODE=draft -> users.drafts.create (review & send by hand)
        SEND_MODE=auto  -> users.messages.send
    Recipient is TEST_RECIPIENT when set (safety override), else email_address.
    Drafts/sends are capped at DAILY_CAP per run.
  - Always write back: outreach_status, email_address, email_source,
    sample_page_url, outreach_date, outreach_notes  (matched by place_id).

Gmail auth: the user's own OAuth refresh token (gmail.compose scope) in
GMAIL_OAUTH_FILE — a service account can't act on a personal Gmail, and only
HTTPS/443 is reachable from the cloud.

Env (see .env.example): GMAIL_ADDRESS, GMAIL_OAUTH_FILE, SEND_MODE, TEST_RECIPIENT,
DAILY_CAP, SHEET_NAME, PAGES_REPO_URL, PAGES_BASE_URL, PREPARED_DIR.
"""

import os
import sys
import json
import glob
import base64
import socket
import subprocess
import datetime
from email.message import EmailMessage
from email.utils import formatdate

import requests
from dotenv import load_dotenv
import gspread
from google.oauth2.credentials import Credentials as UserCredentials
from google.auth.transport.requests import Request as GoogleAuthRequest

from update_sheet import get_credentials, col_index_to_letter

load_dotenv()

# The cloud runner has no IPv6; google/gmail hosts can resolve to IPv6 first and
# fail with "[Errno 97]". Force all DNS resolution to IPv4.
_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    results = _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
    return results or _orig_getaddrinfo(host, port, family, type, proto, flags)


socket.getaddrinfo = _ipv4_only_getaddrinfo

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_OAUTH_FILE = os.getenv("GMAIL_OAUTH_FILE", "gmail_oauth.json")
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]
SEND_MODE = os.getenv("SEND_MODE", "draft").strip().lower()      # draft | auto
TEST_RECIPIENT = os.getenv("TEST_RECIPIENT", "").strip()
DAILY_CAP = int(os.getenv("DAILY_CAP", "25"))
SHEET_NAME = os.getenv("SHEET_NAME", "Hungary Web Prospects")
PAGES_REPO_URL = os.getenv("PAGES_REPO_URL", "")                 # https with token, pushable
PAGES_BASE_URL = os.getenv("PAGES_BASE_URL", "").rstrip("/")     # public github.io base
PREPARED_DIR = os.getenv("PREPARED_DIR", ".tmp/prepared")
PAGES_CLONE = ".tmp/pages_repo"
# Publish pages to this public Google Cloud Storage bucket instead of pushing to
# GitHub Pages: the cloud egress blocks `git push` to github.com (403) but allows
# storage.googleapis.com, and the service account can write objects. Defaults to the
# live bucket so cloud runs work without extra config; set GCS_BUCKET="" to force the
# legacy GitHub-Pages git push instead.
GCS_BUCKET = os.getenv("GCS_BUCKET", "attila-landing-samples").strip()

SENDER = f"Hartmann Attila <{GMAIL_ADDRESS}>"

OUTREACH_COLS = [
    "outreach_status", "email_address", "email_source",
    "sample_page_url", "outreach_date", "outreach_notes", "suggested_domains",
]

FOOTER = (
    "\n\n—\n"
    "Hartmann Attila · webfejlesztő\n"
    f"✉ {GMAIL_ADDRESS}   ·   Weboldal: https://attila-hartmann.github.io/attila-website/?lang=hu\n"
    "LinkedIn: https://www.linkedin.com/in/attila-hartmann-b7b41a24b/\n\n"
    "Ezt a levelet azért kapta, mert nyilvánosan elérhető céges elérhetőséget találtam Önökhöz. "
    "Ha nem kíván több ilyen levelet kapni, válaszoljon ennyivel: „leiratkozás”."
)

# Accent per page theme (mirrors landing_base.html palettes); used to style the e-mail.
THEME_ACCENT = {"warm": "#BC4F2A", "luxe": "#9C6B33", "fresh": "#2F6F5E",
                "sage": "#4A7355", "rose": "#B85C6E"}
DEFAULT_ACCENT = "#2F6F5E"
AVATAR_URL = "https://attila-hartmann.github.io/attila-landing-samples/assets/attila-avatar.jpg"
PORTFOLIO_URL = "https://attila-hartmann.github.io/attila-website/?lang=hu"
LINKEDIN_URL = "https://www.linkedin.com/in/attila-hartmann-b7b41a24b/"
# Static value-props shown under the CTA (ownership / no-lock-in emphasized).
PITCH_BULLETS = [
    ("🎨", "<strong>Egyedi, mobilbarát weboldal</strong> — az Önök arculatára szabva, hogy bizalmat keltsen már az első látogatáskor"),
    ("🔑", "<strong>A domain, a tárhely és a weboldal teljes egészében az Önök tulajdona</strong> — nincsenek kiszolgáltatva egy fejlesztőnek"),
    ("💰", "<strong>Átlátható árazás, egyszeri díj</strong> — rejtett költségek és kellemetlen meglepetések nélkül"),
    ("⚡", "<strong>Gyors elkészítés és hosszú távú támogatás</strong> — ha később módosításra vagy segítségre van szükség, továbbra is számíthatnak rám"),
]

# Fixed paragraphs the script always inserts (NOT agent-generated): the intro just
# above the CTA button, and the closing just above the footer. The agent writes only
# the personalized opener+gap+benefits; these stay identical on every e-mail.
SAMPLE_INTRO = ("Hogy ne csak beszéljek róla, készítettem Önöknek egy ingyenes mintaoldalt, hogy "
                "lássák, hogyan nézhetne ki egy modern weboldal az Önök számára – itt megnézhetik, "
                "kötelezettség nélkül:")
CLOSING = ("Ha úgy érzik, hogy egy modernebb online megjelenés hasznos lenne a vállalkozásuk "
           "számára, kérem válaszoljanak erre az e-mailre, és szívesen megmutatom, hogy milyen "
           "lehetőségeket látok. Egy rövid, kötelezettségmentes konzultáció keretében át tudjuk "
           "beszélni az elképzeléseiket és a lehetőségeket. Ha most nem aktuális, természetesen "
           "nem szükséges reagálniuk.")

# Domain-suggestion settings. Availability is checked with the SYSTEM DNS RESOLVER
# (socket.getaddrinfo), NOT an HTTP API: the cloud sandbox's egress allowlist blocks
# RDAP/DoH/whois endpoints (rdap.verisign.com, dns.google, ...) but the resolver works.
# A name that resolves (apex or www has an A record) is taken; one that fails to
# resolve has no DNS at all => almost certainly unregistered (free).
DOMAIN_TLDS = ["hu", "com"]      # priority order: .hu first (HU SMBs want it), then .com
MAX_DOMAIN_OPTIONS = 3           # show at most this many free domains
MAX_DOMAIN_LOOKUPS = 10          # cap availability checks per business


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


_GCS_SCOPE = "https://www.googleapis.com/auth/devstorage.read_write"


def gcs_upload(place_id, html):
    """Upload <place_id>/index.html to the public GCS bucket; return its public URL.
    Uses the service account over storage.googleapis.com (reachable from the cloud,
    unlike `git push` to github.com). Public read is granted by bucket IAM
    (allUsers → Storage Object Viewer), so no per-object ACL is needed."""
    from google.oauth2 import service_account
    creds = service_account.Credentials.from_service_account_file(
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json"), scopes=[_GCS_SCOPE])
    creds.refresh(GoogleAuthRequest())
    name = f"{place_id}/index.html"
    r = requests.post(
        f"https://storage.googleapis.com/upload/storage/v1/b/{GCS_BUCKET}/o",
        params={"uploadType": "media", "name": name},
        headers={"Authorization": f"Bearer {creds.token}",
                 "Content-Type": "text/html; charset=utf-8",
                 "Cache-Control": "public, max-age=300"},
        data=html.encode("utf-8"), timeout=60,
    )
    if not r.ok:
        raise RuntimeError(f"GCS upload {name} -> {r.status_code}: {r.text[:300]}")
    return f"https://storage.googleapis.com/{GCS_BUCKET}/{name}"


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
import re
import html as _html


def page_style_from_html(html_text):
    """Derive (accent, banner_url) from a generated landing page so the e-mail
    matches it. Falls back to default accent / no banner."""
    # match the <body data-theme="..."> attribute, NOT the CSS rules (body[data-theme="warm"]{...})
    m = re.search(r'<body[^>]*\bdata-theme="(\w+)"', html_text or "")
    accent = THEME_ACCENT.get(m.group(1) if m else "", DEFAULT_ACCENT)
    b = re.search(r"hero-bg[^>]*background-image:url\('([^']+)'\)", html_text or "")
    banner = None
    if b:
        banner = b.group(1).split("?")[0] + "?auto=format&fit=crop&w=600&h=260&q=70"
    return accent, banner


def extract_page_style(index_html_path):
    try:
        with open(index_html_path, encoding="utf-8") as f:
            return page_style_from_html(f.read())
    except OSError:
        return DEFAULT_ACCENT, None


def _paragraphs(text, first_bold=False):
    blocks = [b.strip() for b in (text or "").strip().split("\n\n") if b.strip()]
    out = []
    for i, b in enumerate(blocks):
        esc = _html.escape(b).replace(chr(10), "<br>")
        weight = ";font-weight:700" if (first_bold and i == 0) else ""
        out.append(f'<p style="margin:0 0 16px{weight};">{esc}</p>')
    return "".join(out)


def _pitch_card(accent):
    rows = "".join(
        f'<tr><td width="28" style="font-size:17px;vertical-align:top;line-height:1.5;padding-bottom:9px;">{emoji}</td>'
        f'<td style="font-size:14px;color:#4a4640;line-height:1.5;padding-bottom:9px;font-family:Arial,Helvetica,sans-serif;">{text}</td></tr>'
        for emoji, text in PITCH_BULLETS
    )
    return (
        f'<tr><td style="padding:6px 28px 10px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:#f7f4ef;border-left:3px solid {accent};border-radius:10px;"><tr>'
        f'<td style="padding:18px 22px;">'
        f'<div style="font-family:Georgia,\'Times New Roman\',serif;font-size:15px;font-weight:bold;'
        f'color:#33312e;margin-bottom:12px;">Ha együtt dolgoznánk, erre számíthatnának:</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table>'
        f'</td></tr></table></td></tr>'
    )


def _has_dns(fqdn):
    """True = resolves (apex or www has an A record) => registered/in use.
    False = neither resolves (NXDOMAIN) => almost certainly unregistered.
    None = resolver error. Uses the system resolver, which works in the cloud
    sandbox even though outbound HTTP to RDAP/DoH is blocked by the allowlist."""
    err = False
    for host in (fqdn, "www." + fqdn):
        try:
            socket.getaddrinfo(host, None)
            return True
        except socket.gaierror:
            continue                       # this name has no A record
        except Exception:
            err = True                     # transient resolver failure
    return None if err else False


def domain_is_free(fqdn):
    """True = available, False = taken, None = unknown. NEVER claim free on None."""
    has = _has_dns(fqdn)
    return None if has is None else (not has)


def select_free_domains(stems):
    """Check candidate stems across DOMAIN_TLDS and return up to MAX_DOMAIN_OPTIONS
    confirmed-free FQDNs, preferring .hu. Caps total lookups to guard the API quota."""
    free, lookups = [], 0
    for tld in DOMAIN_TLDS:                  # .hu checked before .com -> .hu preferred
        for stem in stems:
            if len(free) >= MAX_DOMAIN_OPTIONS or lookups >= MAX_DOMAIN_LOOKUPS:
                return free
            stem = (stem or "").strip().lower()
            if not stem:
                continue
            fqdn = f"{stem}.{tld}"
            if fqdn in free:
                continue
            lookups += 1
            if domain_is_free(fqdn) is True:
                free.append(fqdn)
    return free


# Fallback domain stems derived from the business name, used when the agent did
# not supply domain_candidates (agent-written stems are preferred when present).
_HU_MAP = str.maketrans({
    "á": "a", "é": "e", "í": "i", "ó": "o", "ö": "o", "ő": "o", "ú": "u", "ü": "u", "ű": "u",
    "Á": "a", "É": "e", "Í": "i", "Ó": "o", "Ö": "o", "Ő": "o", "Ú": "u", "Ü": "u", "Ű": "u",
})
_STEM_STOPWORDS = {"a", "az", "es", "dr", "kft", "bt", "zrt", "nyrt", "ev", "co", "ltd", "the", "kkt"}


def _ascii_words(text):
    words = re.findall(r"[a-z0-9]+", (text or "").translate(_HU_MAP).lower())
    return [w for w in words if w not in _STEM_STOPWORDS and len(w) > 1]


def _derive_stems(name, city):
    """Brandable lowercase-ASCII stems from a business name/town (fallback only)."""
    nw, cw = _ascii_words(name), _ascii_words(city)
    stems = []
    for s in (
        "".join(nw),                                  # full name
        ("".join(nw) + cw[0]) if (nw and cw) else "",  # name + town
        "".join(nw[:2]),                              # first two words
        (nw[0] + cw[0]) if (nw and cw) else "",        # first word + town
        nw[0] if nw else "",                          # first word
    ):
        if s and s not in stems:
            stems.append(s)
    return stems[:6]


def _domain_card(accent, domains):
    """Card listing confirmed-free domains (mirrors _pitch_card). Empty -> no card."""
    if not domains:
        return ""
    rows = "".join(
        f'<tr><td width="24" style="font-size:15px;vertical-align:top;line-height:1.5;padding-bottom:8px;color:{accent};">✓</td>'
        f'<td style="font-size:15px;color:#33312e;line-height:1.5;padding-bottom:8px;font-family:Arial,Helvetica,sans-serif;">'
        f'<strong>{_html.escape(d)}</strong></td></tr>'
        for d in domains
    )
    return (
        f'<tr><td style="padding:6px 28px 10px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:#f7f4ef;border-left:3px solid {accent};border-radius:10px;"><tr>'
        f'<td style="padding:18px 22px;">'
        f'<div style="font-family:Georgia,\'Times New Roman\',serif;font-size:15px;font-weight:bold;'
        f'color:#33312e;margin-bottom:12px;">Néhány szabad domain név, ami az Önöké lehetne:</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table>'
        f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#a9a399;margin-top:10px;">'
        f'(ezek a domain nevek a levél írásakor szabadnak tűntek)</div>'
        f'</td></tr></table></td></tr>'
    )


def _strip_fixed(body, sample_url):
    """The personalized part only: drop the link token/URL and any echo of the fixed
    intro/closing the agent may have copied from the guidelines example."""
    before = (body or "").partition("{{SAMPLE_PAGE_URL}}")[0]
    for fixed in (SAMPLE_INTRO, CLOSING):
        before = before.replace(fixed, "")
    return before.replace(sample_url, "").strip()


def render_email_html(body, sample_url, accent=DEFAULT_ACCENT, banner_url=None, domains=None):
    """Email-safe HTML (600px table, inline CSS, web-safe fonts, bulletproof button).
    The agent writes only the personalized opener+gap+benefits; the sample-page intro,
    the CTA button, the value/domain cards and the closing are fixed and added here."""
    before = _strip_fixed(body, sample_url)
    banner_row = (
        f'<tr><td style="padding:0;"><img src="{banner_url}" width="600" alt="" '
        f'style="display:block;width:100%;max-width:600px;height:auto;border:0;"></td></tr>'
        if banner_url else ""
    )
    avatar = (
        f'<img src="{AVATAR_URL}" width="36" height="36" alt="Hartmann Attila" '
        f'style="width:36px;height:36px;border-radius:50%;vertical-align:middle;margin-right:11px;border:2px solid rgba(255,255,255,.55);">'
        if AVATAR_URL else
        '<span style="display:inline-block;width:30px;height:30px;line-height:30px;text-align:center;'
        'background:rgba(255,255,255,.2);border-radius:50%;font-size:12px;margin-right:9px;vertical-align:middle;">HA</span>'
    )
    intro_row = (
        f'<tr><td style="padding:4px 28px 2px;color:#33312e;font-size:16px;line-height:1.6;'
        f'font-family:Arial,Helvetica,sans-serif;">{_paragraphs(SAMPLE_INTRO)}</td></tr>'
    )
    closing_row = (
        f'<tr><td style="padding:10px 28px 6px;color:#33312e;font-size:16px;line-height:1.6;'
        f'font-family:Arial,Helvetica,sans-serif;">{_paragraphs(CLOSING)}</td></tr>'
    )
    return f"""<!doctype html><html lang="hu"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f1efe9;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1efe9;">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e7e3da;">
  <tr><td style="background:{accent};padding:14px 26px;">
    <table role="presentation" width="100%"><tr>
      <td style="color:#fff;font-size:16px;font-weight:bold;vertical-align:middle;font-family:Georgia,'Times New Roman',serif;">
        {avatar}Hartmann Attila</td>
      <td align="right" style="vertical-align:middle;font-family:Arial,Helvetica,sans-serif;">
        <div style="color:rgba(255,255,255,.9);font-size:12px;">webfejlesztő</div>
        <div style="font-size:12px;margin-top:3px;">
          <a href="{PORTFOLIO_URL}" target="_blank" style="color:#fff;text-decoration:underline;">Weboldal</a>
          <span style="color:rgba(255,255,255,.55);">·</span>
          <a href="{LINKEDIN_URL}" target="_blank" style="color:#fff;text-decoration:underline;">LinkedIn</a>
        </div></td>
    </tr></table></td></tr>
  {banner_row}
  <tr><td style="padding:30px 28px 6px;color:#33312e;font-size:16px;line-height:1.6;font-family:Arial,Helvetica,sans-serif;">{_paragraphs(before, first_bold=True)}</td></tr>
  {intro_row}
  <tr><td align="center" style="padding:12px 28px 18px;">
    <table role="presentation" cellpadding="0" cellspacing="0"><tr>
      <td style="border-radius:10px;background:{accent};">
        <a href="{sample_url}" target="_blank" style="display:inline-block;padding:15px 32px;font-family:Arial,sans-serif;font-size:16px;font-weight:bold;color:#ffffff;text-decoration:none;border-radius:10px;">Megnézem a mintaoldalt →</a>
      </td></tr></table></td></tr>
  {_pitch_card(accent)}
  {_domain_card(accent, domains or [])}
  {closing_row}
  <tr><td style="padding:22px 28px;background:#faf8f4;border-top:1px solid #eee7db;color:#8a857c;font-size:13px;line-height:1.6;font-family:Arial,Helvetica,sans-serif;">
    <strong style="color:#33312e;">Hartmann Attila</strong> · webfejlesztő<br>
    ✉ <a href="mailto:{GMAIL_ADDRESS}" style="color:{accent};text-decoration:none;">{GMAIL_ADDRESS}</a>
    &nbsp;·&nbsp; <a href="https://attila-hartmann.github.io/attila-website/?lang=hu" style="color:{accent};text-decoration:none;">Weboldal</a>
    &nbsp;·&nbsp; <a href="https://www.linkedin.com/in/attila-hartmann-b7b41a24b/" style="color:{accent};text-decoration:none;">LinkedIn</a>
    <br><br><span style="color:#a9a399;font-size:12px;">Ezt a levelet azért kapta, mert nyilvánosan elérhető céges elérhetőséget találtam Önökhöz. Ha nem kíván több ilyen levelet kapni, válaszoljon ennyivel: „leiratkozás”.</span>
  </td></tr>
</table>
<div style="color:#b8b2a8;font-size:11px;margin-top:14px;font-family:Arial,sans-serif;">Fotó: Unsplash</div>
</td></tr></table></body></html>"""


def build_message(to_addr, subject, body, sample_url, accent=DEFAULT_ACCENT,
                  banner_url=None, domains=None):
    # plain-text part (fallback + deliverability) — mirrors the HTML order:
    # personalized body, fixed intro, sample link, domain options, fixed closing, footer.
    text_body = _strip_fixed(body, sample_url)
    text_body += "\n\n" + SAMPLE_INTRO + "\n\n" + sample_url
    if domains:
        text_body += ("\n\nNéhány szabad domain név, ami az Önöké lehetne:\n"
                      + "\n".join(f"  ✓ {d}" for d in domains)
                      + "\n(ezek a domain nevek a levél írásakor szabadnak tűntek)")
    text_body += "\n\n" + CLOSING + FOOTER

    msg = EmailMessage()
    msg["From"] = SENDER
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(text_body)
    msg.add_alternative(render_email_html(body, sample_url, accent, banner_url, domains),
                        subtype="html")
    return msg


# Gmail REST API over HTTPS — the cloud blocks IMAP/SMTP ports, and a service
# account can't act on a personal Gmail, so we use the user's OAuth refresh token.
_GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


def gmail_access_token():
    """Load the user's OAuth refresh token and exchange it for an access token."""
    if not os.path.exists(GMAIL_OAUTH_FILE):
        raise RuntimeError(f"GMAIL_OAUTH_FILE '{GMAIL_OAUTH_FILE}' not found.")
    with open(GMAIL_OAUTH_FILE, encoding="utf-8") as f:
        info = json.load(f)
    creds = UserCredentials(
        token=None,
        refresh_token=info["refresh_token"],
        client_id=info["client_id"],
        client_secret=info["client_secret"],
        token_uri=info.get("token_uri", "https://oauth2.googleapis.com/token"),
        scopes=GMAIL_SCOPES,
    )
    creds.refresh(GoogleAuthRequest())
    return creds.token


def _gmail_post(path, payload, token):
    r = requests.post(
        f"{_GMAIL_API}/{path}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"Gmail API {path} -> {r.status_code}: {r.text[:300]}")
    return r.json()


def _raw(msg):
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def create_draft(msg, token):
    _gmail_post("drafts", {"message": {"raw": _raw(msg)}}, token)


def send_now(msg, token):
    _gmail_post("messages/send", {"raw": _raw(msg)}, token)


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
    if missing:
        new_col_count = len(headers) + len(missing)
        if new_col_count > ws.col_count:
            ws.resize(rows=ws.row_count, cols=new_col_count)
        for i, name in enumerate(missing):
            ws.update_cell(1, len(headers) + 1 + i, name)
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


def load_email_json(path):
    """Read an agent-written email.json, self-healing the recurring bug where a
    Hungarian „…" quote's closing mark was written as an ASCII " (U+0022) inside a
    JSON string, prematurely ending it and raising JSONDecodeError."""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        repaired = re.sub(r'„([^"„\n]*?)"(?!\s*[:,}\]])', r'„\1”', raw)
        return json.loads(repaired)  # raises again only if it's a different problem


def load_queue_map():
    """place_id -> business record from .tmp/queue.json (for fallback domain stems)."""
    qpath = os.path.join(os.path.dirname(PREPARED_DIR) or ".", "queue.json")
    try:
        with open(qpath, encoding="utf-8") as f:
            return {str(it.get("place_id", "")): it for it in json.load(f)}
    except (OSError, ValueError):
        return {}


# ---------------------------------------------------------------------- main ---
def main():
    if not GMAIL_ADDRESS or not os.path.exists(GMAIL_OAUTH_FILE):
        print(f"GMAIL_ADDRESS unset or GMAIL_OAUTH_FILE '{GMAIL_OAUTH_FILE}' missing.",
              file=sys.stderr)
        sys.exit(1)

    today = datetime.date.today().isoformat()
    queue_by_id = load_queue_map()  # business facts for fallback domain stems
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
        try:
            e = load_email_json(ejson)
        except Exception as exc:  # one malformed file must not abort the whole run
            print(f"  ERROR parsing {ejson}: {exc}", file=sys.stderr)
            results.append({
                "place_id": os.path.basename(d), "outreach_status": "error",
                "email_address": "", "email_source": "", "sample_page_url": "",
                "outreach_date": today, "outreach_notes": f"email.json parse hiba: {exc}",
                "suggested_domains": "",
            })
            continue
        pid = str(e.get("place_id", os.path.basename(d)))
        if not e.get("email_address"):
            results.append({
                "place_id": pid, "outreach_status": "no_email",
                "email_address": "", "email_source": e.get("email_source", ""),
                "sample_page_url": "", "outreach_date": today,
                "outreach_notes": e.get("notes", "nem található e-mail cím"),
                "suggested_domains": "",
            })
        else:
            e["_dir"] = d
            e["place_id"] = pid
            sendable.append(e)

    # Publish pages for sendable (up to cap), then draft/send.
    use_gcs = bool(GCS_BUCKET)            # GCS in the cloud (github push is blocked); git locally
    if not use_gcs:
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
        if use_gcs:
            with open(page, encoding="utf-8") as f:
                e["_url"] = gcs_upload(e["place_id"], f.read())
        else:
            e["_url"] = stage_page(e["place_id"], page)
        staged += 1
    if staged and use_gcs:
        print(f"Uploaded {staged} page(s) to GCS bucket '{GCS_BUCKET}'.")
    elif staged:
        push_pages(staged)

    token = gmail_access_token()  # one access token for the whole batch

    for e in capped:
        if e.get("_skip"):
            results.append({
                "place_id": e["place_id"], "outreach_status": "skip",
                "email_address": e["email_address"], "email_source": e.get("email_source", ""),
                "sample_page_url": "", "outreach_date": today,
                "outreach_notes": e["_skip"], "suggested_domains": "",
            })
            continue

        recipient = TEST_RECIPIENT or e["email_address"]
        subject = e["subject"]
        if TEST_RECIPIENT:
            subject = f"[TESZT → {e['email_address']}] {subject}"
        accent, banner = extract_page_style(os.path.join(e["_dir"], "index.html"))
        stems = e.get("domain_candidates") or []
        if not stems:  # fallback: derive from the business name in the queue
            biz = queue_by_id.get(e["place_id"], {})
            stems = _derive_stems(biz.get("name", ""), biz.get("city", ""))
        domains = select_free_domains(stems)
        msg = build_message(recipient, subject, e["body"], e["_url"], accent, banner, domains)

        try:
            if SEND_MODE == "auto":
                send_now(msg, token)
                status, verb = "sent", "Sent"
            else:
                create_draft(msg, token)
                status, verb = "drafted", "Drafted"
            print(f"  {verb}: {e['email_address']}  → {recipient}  ({e['_url']})")
            note = e.get("notes", "")
            if TEST_RECIPIENT:
                note = (note + " | TESZT küldés").strip(" |")
        except Exception as exc:
            status = "error"  # NOT in ALREADY_HANDLED_STATUSES -> retried next run
            note = f"küldés/draft hiba: {exc}"
            print(f"  ERROR for {e['email_address']}: {exc}", file=sys.stderr)

        results.append({
            "place_id": e["place_id"], "outreach_status": status,
            "email_address": e["email_address"], "email_source": e.get("email_source", ""),
            "sample_page_url": e["_url"], "outreach_date": today,
            "outreach_notes": note, "suggested_domains": ", ".join(domains),
        })

    # Single batched write-back.
    ws = open_ws()
    colmap = ensure_columns(ws)
    rowmap = row_map(ws)
    writeback(ws, colmap, rowmap, results)

    drafted = sum(1 for r in results if r["outreach_status"] in ("drafted", "sent"))
    no_email = sum(1 for r in results if r["outreach_status"] == "no_email")
    skipped = sum(1 for r in results if r["outreach_status"] == "skip")
    errored = sum(1 for r in results if r["outreach_status"] == "error")
    print(f"\nDone. mode={SEND_MODE} cap={DAILY_CAP} "
          f"| {drafted} {'sent' if SEND_MODE=='auto' else 'drafted'}, "
          f"{no_email} no_email, {skipped} skipped, {errored} error (will retry).")


if __name__ == "__main__":
    main()
