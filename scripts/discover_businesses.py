#!/usr/bin/env python3
"""
Discover businesses using Google Places API (New) — Text Search endpoint.
"""

import os
import sys
import json
import argparse
import requests
from urllib.parse import urlparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"

FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.rating",
    "places.userRatingCount",
    "places.businessStatus",
    "nextPageToken",
])

HUNGARIAN_CITIES = {
    "budapest", "debrecen", "miskolc", "pécs", "győr", "nyíregyháza",
    "kecskemét", "székesfehérvár", "szombathely", "szolnok", "kaposvár",
    "érd", "veszprém", "zalaegerszeg", "sopron", "eger", "békéscsaba",
    "tatabánya", "nagykanizsa", "dunaújváros", "hódmezővásárhely",
}

# Domains that indicate a social-media-only presence rather than a real website
SOCIAL_DOMAINS = {
    "facebook.com", "fb.com", "m.facebook.com",
    "instagram.com", "twitter.com", "x.com",
    "linkedin.com", "tiktok.com",
}

def classify_website(uri):
    """
    Returns (website, has_website, website_type, social_url).
    website_type: "real" | "social_only" | "none"
    """
    if not uri:
        return None, False, "none", None
    try:
        netloc = urlparse(uri).netloc.lower().lstrip("www.")
        if any(netloc == sd or netloc.endswith("." + sd) for sd in SOCIAL_DOMAINS):
            return None, False, "social_only", uri
    except Exception:
        pass
    return uri, True, "real", None

def extract_city(formatted_address):
    parts = [p.strip() for p in formatted_address.split(",")]
    for part in parts:
        if any(city in part.lower() for city in HUNGARIAN_CITIES):
            return part
    return parts[-2] if len(parts) >= 2 else formatted_address

def search_places(query, location, max_results, api_key):
    businesses = []
    page_token = None
    full_query = f"{query} {location}"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }

    while len(businesses) < max_results:
        body = {"textQuery": full_query, "languageCode": "hu"}
        if page_token:
            body["pageToken"] = page_token

        resp = requests.post(PLACES_URL, headers=headers, json=body, timeout=15)

        if resp.status_code != 200:
            print(f"API error {resp.status_code}: {resp.text}", file=sys.stderr)
            break

        data = resp.json()
        places = data.get("places", [])

        if not places:
            break

        for place in places:
            name = place.get("displayName", {}).get("text")
            address = place.get("formattedAddress", "")
            raw_uri = place.get("websiteUri")
            website, has_website, website_type, social_url = classify_website(raw_uri)
            businesses.append({
                "name": name,
                "address": address,
                "city": extract_city(address),
                "industry": query,
                "google_rating": place.get("rating"),
                "review_count": place.get("userRatingCount", 0),
                "place_id": place.get("id"),
                "phone": place.get("nationalPhoneNumber"),
                "website": website,
                "has_website": has_website,
                "website_type": website_type,
                "social_url": social_url,
                "business_status": place.get("businessStatus", ""),
                "status": "New",
                "notes": "",
                "date_added": datetime.now().strftime("%Y-%m-%d"),
            })
            if len(businesses) >= max_results:
                break

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return businesses

def main():
    parser = argparse.ArgumentParser(description="Discover businesses via Google Places API (New)")
    parser.add_argument("--query", required=True, help='Industry term (e.g. "fogorvos")')
    parser.add_argument("--location", required=True, help='Location (e.g. "Budapest")')
    parser.add_argument("--max_results", type=int, default=50)
    parser.add_argument("--output", help="Output JSON path (default: .tmp/businesses_<ts>.json)")
    parser.add_argument("--a_candidates_only", action="store_true",
        help="Discard businesses that cannot score A before website evaluation")
    args = parser.parse_args()

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("Error: GOOGLE_MAPS_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    os.makedirs(".tmp", exist_ok=True)
    output = args.output or f".tmp/businesses_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    print(f"Searching '{args.query}' in '{args.location}' (max {args.max_results})...")
    businesses = search_places(args.query, args.location, args.max_results, api_key)

    if args.a_candidates_only:
        before = len(businesses)
        businesses = [
            b for b in businesses
            if b["website_type"] == "real"
            or (b["website_type"] == "social_only" and (b.get("review_count") or 0) > 0)
            or (b["website_type"] == "none"        and (b.get("review_count") or 0) > 0)
        ]
        print(f"A-candidate filter: {before} → {len(businesses)} businesses retained")

    with open(output, "w", encoding="utf-8") as f:
        json.dump(businesses, f, ensure_ascii=False, indent=2)

    no_website = sum(1 for b in businesses if b["website_type"] == "none")
    social_only = sum(1 for b in businesses if b["website_type"] == "social_only")
    print(f"Found {len(businesses)} businesses — {no_website} no website, {social_only} social-only, {len(businesses)-no_website-social_only} real website. Saved to {output}")

if __name__ == "__main__":
    main()
