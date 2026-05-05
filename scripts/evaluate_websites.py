#!/usr/bin/env python3
"""
Evaluate websites: PageSpeed Insights, SSL, mobile-friendliness, tech stack detection.
"""

import os
import sys
import ssl
import json
import socket
import argparse
import requests
from urllib.parse import urlparse
from datetime import datetime
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()

SOCIAL_DOMAINS = {
    "facebook.com", "fb.com", "m.facebook.com",
    "instagram.com", "twitter.com", "x.com",
    "linkedin.com", "tiktok.com",
}

def is_social_url(url):
    try:
        netloc = urlparse(url).netloc.lower().lstrip("www.")
        return any(netloc == sd or netloc.endswith("." + sd) for sd in SOCIAL_DOMAINS)
    except Exception:
        return False

def check_ssl(url):
    try:
        hostname = url.replace("https://", "").replace("http://", "").split("/")[0]
        ctx = ssl.create_default_context()
        conn = ctx.wrap_socket(socket.socket(), server_hostname=hostname)
        conn.settimeout(5)
        conn.connect((hostname, 443))
        conn.close()
        return True
    except Exception:
        return False

def detect_tech_stack(html):
    html_lower = html.lower()
    hints = []
    if "wp-content/" in html_lower or "wordpress" in html_lower:
        hints.append("WordPress")
    if "wix.com" in html_lower or "_wix_" in html_lower:
        hints.append("Wix")
    if "squarespace" in html_lower:
        hints.append("Squarespace")
    if "weebly" in html_lower:
        hints.append("Weebly")
    if "joomla" in html_lower:
        hints.append("Joomla")
    if "drupal" in html_lower:
        hints.append("Drupal")
    if "shopify" in html_lower:
        hints.append("Shopify")
    return ", ".join(hints) if hints else "Custom/Unknown"

def run_pagespeed(url, api_key):
    params = {"url": url, "strategy": "mobile"}
    if api_key:
        params["key"] = api_key
    try:
        resp = requests.get(
            "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
            params=params,
            timeout=40,
        )
        data = resp.json()
        lhr = data.get("lighthouseResult", {})
        categories = lhr.get("categories", {})
        perf_score = categories.get("performance", {}).get("score")
        viewport_audit = lhr.get("audits", {}).get("viewport", {})
        mobile_friendly = viewport_audit.get("score", 0) == 1
        return {
            "site_score": round(perf_score * 100) if perf_score is not None else None,
            "mobile_friendly": mobile_friendly,
        }
    except Exception:
        # PageSpeed failure doesn't mean the site is down — return no data
        return {"site_score": None, "mobile_friendly": None}

def make_verdict(result):
    if not result.get("site_loads"):
        return "Broken/unreachable"
    score = result.get("site_score")
    if score is not None and score < 30:
        return "Very slow/broken"
    if not result.get("ssl"):
        return "No SSL"
    if result.get("mobile_friendly") is False:  # None = PageSpeed didn't run, not the same as False
        return "Not mobile-friendly"
    if score is not None and score < 50:
        return "Slow"
    tech = result.get("tech_stack", "")
    if any(t in tech for t in ("Wix", "Squarespace", "Weebly", "WordPress")):
        return "Template-based"
    return "Functional"

def evaluate_website(business, skip_pagespeed=False):
    result = business.copy()
    result.update({
        "site_score": None, "mobile_friendly": None, "ssl": None,
        "tech_stack": None, "site_loads": None, "site_verdict": None,
    })

    # Social-only: already classified at discovery time — no further evaluation needed
    if business.get("website_type") == "social_only":
        result["site_verdict"] = "Social only"
        result["site_loads"] = True
        result["tech_stack"] = "Social media"
        return result

    if not business.get("website"):
        result["site_verdict"] = "No website"
        return result

    url = business["website"]
    api_key = os.getenv("PAGESPEED_API_KEY", "")

    # Direct HTTP fetch is the authoritative check for site_loads and tech stack.
    # PageSpeed failures (rate limits, timeouts) must not affect this.
    try:
        resp = requests.get(
            url, timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            allow_redirects=True,
        )
        # Detect domains that redirect to social media (e.g. domain.hu → facebook.com/pagename)
        if is_social_url(resp.url):
            result["site_loads"] = True
            result["tech_stack"] = "Social redirect"
            result["site_verdict"] = "Social only"
            result["website_type"] = "social_only"
            result["social_url"] = resp.url
            result["website"] = None
            result["has_website"] = False
            return result
        result["site_loads"] = resp.status_code < 500
        result["tech_stack"] = detect_tech_stack(resp.text)
    except Exception:
        result["site_loads"] = False
        result["tech_stack"] = "Unknown"

    result["ssl"] = check_ssl(url)

    # Only call PageSpeed if site actually loads (saves quota and time)
    if result["site_loads"] and not skip_pagespeed:
        ps = run_pagespeed(url, api_key)
        result["site_score"] = ps.get("site_score")
        result["mobile_friendly"] = ps.get("mobile_friendly")

    result["site_verdict"] = make_verdict(result)
    return result

def main():
    parser = argparse.ArgumentParser(description="Evaluate websites for prospects")
    parser.add_argument("input_file", help="JSON from discover_businesses.py")
    parser.add_argument("--output", help="Output JSON path")
    parser.add_argument("--workers", type=int, default=5, help="Parallel workers (default: 5)")
    parser.add_argument("--skip_pagespeed", action="store_true",
        help="Skip PageSpeed API calls (faster; sufficient for A-grade-only runs)")
    args = parser.parse_args()

    with open(args.input_file, "r", encoding="utf-8") as f:
        businesses = json.load(f)

    output = args.output or f".tmp/evaluated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    os.makedirs(".tmp", exist_ok=True)
    print(f"Evaluating {len(businesses)} businesses ({args.workers} workers)...")

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(evaluate_website, b, args.skip_pagespeed): b for b in businesses}
        for i, future in enumerate(as_completed(futures), 1):
            r = future.result()
            results.append(r)
            print(f"  [{i}/{len(businesses)}] {r.get('name', '?')}: {r.get('site_verdict', '?')}")

    with open(output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Done. Saved to {output}")

if __name__ == "__main__":
    main()
