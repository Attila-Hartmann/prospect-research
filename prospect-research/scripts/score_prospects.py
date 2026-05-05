#!/usr/bin/env python3
"""
Score prospects A/B/C/D based on digital presence rules and sort by priority.
"""

import sys
import json
import argparse
from datetime import datetime

HIGH_VALUE_INDUSTRIES = {
    "fogorvos", "orvos", "ügyvéd", "ingatlan", "dentist", "doctor",
    "lawyer", "medical", "dental", "legal", "real estate", "fogászat",
}

SCORE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}

def score_prospect(business):
    result = business.copy()

    has_website = business.get("has_website", False)
    website_type = business.get("website_type", "real" if has_website else "none")
    site_score = business.get("site_score")
    mobile_friendly = business.get("mobile_friendly", True)
    ssl_ok = business.get("ssl", True)
    site_loads = business.get("site_loads", True)
    review_count = business.get("review_count") or 0
    site_verdict = business.get("site_verdict", "")
    industry = str(business.get("industry", "")).lower()
    business_status = business.get("business_status", "")

    # Hard skip
    if business_status == "CLOSED_PERMANENTLY":
        result["prospect_score"] = "D"
        result["recommended_approach"] = "Skip — permanently closed"
        return result

    is_high_value = any(term in industry for term in HIGH_VALUE_INDUSTRIES)

    # A-tier: immediate priority
    if website_type == "social_only" and review_count > 0:
        result["prospect_score"] = "A"
        result["recommended_approach"] = "Facebook/Instagram only — active business with zero real web presence, strong opener"
    elif website_type == "none" and review_count > 0:
        result["prospect_score"] = "A"
        result["recommended_approach"] = "Active on Google Maps but zero web presence — lead with that gap"
    elif has_website and (not site_loads or site_verdict == "Broken/unreachable"):
        result["prospect_score"] = "A"
        result["recommended_approach"] = "Website exists but is broken/unreachable — clear pain point"
    elif has_website and not ssl_ok:
        result["prospect_score"] = "A"
        result["recommended_approach"] = "No SSL — security pitch, easy win"

    # B-tier: warm
    elif website_type == "social_only":
        result["prospect_score"] = "B"
        result["recommended_approach"] = "Social media only, no reviews — uncertain activity, worth a check"
    elif has_website and not mobile_friendly:
        result["prospect_score"] = "B"
        result["recommended_approach"] = "Not mobile-friendly — direct upgrade pitch"
    elif has_website and site_score is not None and site_score < 50:
        result["prospect_score"] = "B"
        result["recommended_approach"] = "Very slow site (PageSpeed < 50) — performance pitch"
    elif is_high_value and has_website and site_verdict in ("Slow", "Template-based", "Not mobile-friendly"):
        result["prospect_score"] = "B"
        result["recommended_approach"] = "High-value industry with underperforming site"

    # C-tier: lukewarm
    elif has_website and site_verdict == "Template-based":
        result["prospect_score"] = "C"
        result["recommended_approach"] = "Template site — differentiation/branding pitch"
    elif not has_website:
        result["prospect_score"] = "C"
        result["recommended_approach"] = "No website, no reviews — uncertain viability, low priority"

    # D-tier: skip
    else:
        result["prospect_score"] = "D"
        result["recommended_approach"] = "Decent web presence — monitor for changes"

    return result

def main():
    parser = argparse.ArgumentParser(description="Score and rank prospects A/B/C/D")
    parser.add_argument("input_file", help="JSON from evaluate_websites.py")
    parser.add_argument("--output", help="Output JSON path")
    parser.add_argument("--min_grade", choices=["A", "B", "C", "D"], default=None,
        help="Only output prospects at this grade or better (A is best)")
    args = parser.parse_args()

    with open(args.input_file, "r", encoding="utf-8") as f:
        businesses = json.load(f)

    scored = [score_prospect(b) for b in businesses]
    scored.sort(
        key=lambda b: (
            SCORE_ORDER.get(b.get("prospect_score"), 4),
            -(b.get("review_count") or 0),
        )
    )

    if args.min_grade:
        threshold = SCORE_ORDER[args.min_grade]
        before = len(scored)
        scored = [b for b in scored if SCORE_ORDER.get(b.get("prospect_score"), 4) <= threshold]
        print(f"Grade filter (>= {args.min_grade}): {before} → {len(scored)} prospects retained")

    output = args.output or f".tmp/scored_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(scored, f, ensure_ascii=False, indent=2)

    counts = {g: sum(1 for b in scored if b.get("prospect_score") == g) for g in "ABCD"}
    print(f"Scored {len(scored)} prospects — A:{counts['A']} B:{counts['B']} C:{counts['C']} D:{counts['D']}")
    print(f"Saved to {output}")

if __name__ == "__main__":
    main()
