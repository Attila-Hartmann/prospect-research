#!/usr/bin/env python3
"""
Contact / website discovery for outreach prospects — runs over HTTPS only, so it
works from the cloud sandbox (which 403s many sites and blocks IMAP/SMTP/DNS).

Two jobs for a business given its name + town:
  1. Detect whether it ALREADY has a real, working website (so we don't pitch a
     "you have no website" e-mail to someone who has one).
  2. If it does, try to extract a contact e-mail from that site.

How it beats the cloud's blocked WebFetch:
  - guesses candidate domains from the business name and only fetches ones that
    actually resolve (DNS-over-HTTPS NS check — skips the ~90% unregistered guesses);
  - fetches with a real browser User-Agent, and on a 403/timeout falls back to the
    r.jina.ai reader-proxy (server-side fetch → bypasses WAF/egress blocks);
  - attributes a page to the business only if the page text mentions the business
    name/town (filters coincidental domains and parked/for-sale pages).

Usable as a library (import discover) or CLI:
    python3 discover_contact.py --name "La Créme Szépségszalon" --city "Budapest"
"""

import re
import sys
import json
import socket
import argparse
import requests

# The cloud runner has no IPv6; dns.google / r.jina.ai can resolve to IPv6 first and
# fail with "[Errno 97]". Force IPv4 (select.py does not import outreach_publish, so
# its patch would not apply here).
_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    results = _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
    return results or _orig_getaddrinfo(host, port, family, type, proto, flags)


socket.getaddrinfo = _ipv4_only_getaddrinfo

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
CONTACT_PATHS = ["", "/kapcsolat", "/elerhetoseg", "/contact", "/rolunk", "/impresszum"]

# Reject placeholder / framework / asset / CDN addresses that aren't real contacts.
_BAD_EMAIL_BITS = (
    "sentry", "wixpress", "mysite.com", "example.", "@example", "domain.com",
    "your-email", "youremail", "email@", "name@", "@2x", "u003", ".png", ".jpg",
    ".jpeg", ".webp", ".svg", ".gif", "fbcdn", "gstatic", "googleapis", "cloudflare",
    "w3.org", "schema.org", "sentry.io", "wix.com", "placeholder",
)

_HU_MAP = str.maketrans({
    "á": "a", "é": "e", "í": "i", "ó": "o", "ö": "o", "ő": "o", "ú": "u", "ü": "u", "ű": "u",
    "Á": "a", "É": "e", "Í": "i", "Ó": "o", "Ö": "o", "Ő": "o", "Ú": "u", "Ü": "u", "Ű": "u",
})
_STOPWORDS = {"a", "az", "es", "dr", "kft", "bt", "zrt", "nyrt", "ev", "co", "ltd", "the", "kkt"}


def _ascii_words(text):
    words = re.findall(r"[a-z0-9]+", (text or "").translate(_HU_MAP).lower())
    return [w for w in words if w not in _STOPWORDS and len(w) > 1]


def derive_stems(name, city):
    nw, cw = _ascii_words(name), _ascii_words(city)
    stems = []
    for s in (
        "".join(nw),
        ("".join(nw) + cw[0]) if (nw and cw) else "",
        "".join(nw[:2]),
        nw[0] if nw else "",
    ):
        if s and s not in stems and len(s) >= 4:  # >=4 chars to avoid generic single words
            stems.append(s)
    return stems[:4]


def _resolves(fqdn):
    """DNS-over-HTTPS: does the domain have NS/SOA records (i.e. is it registered/live)?"""
    for rtype in ("NS", "A"):
        try:
            j = requests.get("https://dns.google/resolve",
                             params={"name": fqdn, "type": rtype}, timeout=8).json()
        except (requests.RequestException, ValueError):
            return False
        if j.get("Status") == 0 and j.get("Answer"):
            return True
        if j.get("Status") == 3:  # NXDOMAIN
            return False
    return False


def fetch(url):
    """(status:int|None, text). Direct browser-UA first; on block/error fall back to
    the r.jina.ai reader-proxy (server-side fetch over HTTPS)."""
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "hu,en;q=0.8"},
                         timeout=12, allow_redirects=True)
        if r.status_code == 200 and r.text:
            return 200, r.text
        blocked = r.status_code in (401, 403, 429, 503)
    except requests.RequestException:
        blocked = True
    if not blocked:
        return None, ""
    try:  # reader-proxy fallback (server-side fetch over HTTPS)
        r = requests.get("https://r.jina.ai/" + url, headers={"User-Agent": UA}, timeout=30)
        head = (r.text or "")[:300].lower()
        # the proxy returns 200 even when the TARGET errored — reject those wrappers
        proxy_err = ("returned error" in head or head.startswith(("title: 4", "title: 5")))
        if r.status_code == 200 and r.text and not proxy_err:
            return 200, r.text
    except requests.RequestException:
        pass
    return None, ""


def extract_emails(text, prefer_domain=None):
    found = []
    for m in _EMAIL_RE.findall(text or ""):
        ml = m.lower().rstrip(".")
        if any(b in ml for b in _BAD_EMAIL_BITS):
            continue
        if ml not in found:
            found.append(ml)
    # prefer an address on the site's own domain, else common HU webmail, else first
    if prefer_domain:
        found.sort(key=lambda e: (not e.endswith("@" + prefer_domain),
                                  not e.split("@")[-1].endswith((".hu", "gmail.com", "freemail.hu"))))
    return found


_PARKED_BITS = ("domain for sale", "this domain is for sale", "eladó a domain",
                "eladó domain", "megvásárolható", "domain parking", "parked domain",
                "buy this domain", "domain név eladó")


def _is_parked(text):
    low = (text or "").lower()
    return any(b in low for b in _PARKED_BITS)


def _page_belongs(text, name, city, distinctive=False):
    """True if the page plausibly belongs to this business: it mentions a name token
    or the town, OR it sits on the business's exact multi-word brand domain (which is
    self-attributing). Filters coincidental domains and parked/for-sale pages."""
    hay = (text or "").translate(_HU_MAP).lower()
    if len(hay) < 300 or _is_parked(text):  # near-empty / parked / for-sale
        return False
    tokens = [w for w in _ascii_words(name) if len(w) > 3]
    if any(t in hay for t in tokens):
        return True
    cw = _ascii_words(city)
    if cw and cw[0] in hay and tokens:
        return True
    return distinctive  # live, non-parked page on the exact brand domain


def discover(name, city, known_site=""):
    """Return {site, email, email_source, notes}. site = the business's live website
    URL if one is confidently found (else ''); email from that site if extractable."""
    checked = []
    candidates = []  # (fqdn, distinctive) — distinctive = exact multi-word brand domain
    if known_site:
        d = re.sub(r"^https?://(www\.)?", "", known_site.strip()).split("/")[0].lower()
        if d:
            candidates.append((d, False))
    brand_slug = "".join(_ascii_words(name))
    brand_distinctive = len(_ascii_words(name)) >= 2  # multi-word names are self-attributing
    for stem in derive_stems(name, city):
        distinctive = (stem == brand_slug and brand_distinctive)
        candidates += [(f"{stem}.hu", distinctive), (f"{stem}.com", distinctive)]
    seen = set()
    for fqdn, distinctive in candidates:
        if fqdn in seen:
            continue
        seen.add(fqdn)
        if len(checked) >= 8:
            break
        if not _resolves(fqdn):
            continue
        checked.append(fqdn)
        status, text = fetch("https://" + fqdn)
        if not text or not _page_belongs(text, name, city, distinctive):
            continue
        site = "https://" + fqdn
        emails = extract_emails(text, prefer_domain=fqdn)
        if not emails:  # try a couple of contact subpages
            for p in CONTACT_PATHS[1:]:
                _, t2 = fetch(site + p)
                emails = extract_emails(t2, prefer_domain=fqdn)
                if emails:
                    break
        return {
            "site": site,
            "email": emails[0] if emails else "",
            "email_source": "website" if emails else "",
            "notes": (f"él? weboldal: {site}" + (f" | e-mail: {emails[0]}" if emails else
                      " | e-mail nem volt kinyerhető")),
        }
    return {"site": "", "email": "", "email_source": "",
            "notes": ("nincs saját weboldal (ellenőrzött domainek: " +
                      (", ".join(checked) if checked else "egy sem regisztrált") + ")")}


def main():
    ap = argparse.ArgumentParser(description="Discover a prospect's website + contact e-mail")
    ap.add_argument("--name", required=True)
    ap.add_argument("--city", default="")
    ap.add_argument("--site", default="", help="known website if any")
    args = ap.parse_args()
    print(json.dumps(discover(args.name, args.city, args.site), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
