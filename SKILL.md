---
name: prospect-research
description: Discover and evaluate local businesses in Hungary as prospects for web development services. Searches Google Maps/Places for businesses by industry and location, evaluates their website quality (PageSpeed, SSL, mobile-friendliness, tech stack), scores them A-D based on conversion probability, and saves a ranked prospect list to Google Sheets. Use when asked to find prospects, research businesses, or build a lead list for a target industry and location in Hungary.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Prospect Research & Lead Scoring

## Goal
Discover local businesses by industry and location in Hungary, evaluate their digital presence (website quality, Google rating, mobile/SSL status), score them A–D based on conversion probability, and save a ranked prospect list to Google Sheets.

## Inputs
- **Industry**: Hungarian or English term (e.g., `"fogorvos"`, `"étterem"`, `"ügyvéd"`, `"autószerelő"`)
- **Location**: Hungarian city or region (e.g., `"Budapest"`, `"Debrecen"`, `"Pest megye"`)
- **Max Results**: How many businesses to discover (default: 50; Google Places caps at ~60 per query)

## Scripts
All scripts are in `./scripts/`:
- `discover_businesses.py` — Google Places Text Search + Place Details → JSON
- `evaluate_websites.py` — PageSpeed Insights + SSL + mobile + tech stack → JSON
- `score_prospects.py` — Rule-based A/B/C/D scoring, sorted by priority → JSON
- `update_sheet.py` — Upload ranked JSON to Google Sheets

## Process

### Standard Run

1. **Discover businesses**
   ```bash
   python3 ./scripts/discover_businesses.py --query "INDUSTRY" --location "LOCATION" --max_results 50 --output .tmp/businesses.json
   ```

2. **Verify discovery quality**
   - Read `.tmp/businesses.json`
   - Confirm at least 80% of results match the intended industry + location
   - **Pass**: Proceed to step 3
   - **Fail**: Stop — ask user to refine query or try English synonym

3. **Evaluate websites**
   ```bash
   python3 ./scripts/evaluate_websites.py .tmp/businesses.json --output .tmp/evaluated.json --workers 5
   ```
   Note: contacts each business's website. Expect 10–30 seconds per business.

4. **Score prospects**
   ```bash
   python3 ./scripts/score_prospects.py .tmp/evaluated.json --output .tmp/scored.json
   ```

5. **Upload to Google Sheet**
   ```bash
   python3 ./scripts/update_sheet.py .tmp/scored.json --sheet_name "Prospects - INDUSTRY LOCATION"
   ```
   Report the returned Google Sheet URL to the user.

## Outputs
**The ONLY deliverable is the Google Sheet URL.** Local `.tmp/` JSON files are temporary intermediates.

Sheet columns: Business Name | Industry | City | Prospect Score | Recommended Approach | Website | Has Website | Site Score | Mobile Friendly | SSL | Tech Stack | Site Verdict | Google Rating | Review Count | Phone | Status | Notes | Date Added

## Scoring Rules
- **A (Hot)**: Facebook/Instagram only + has reviews, OR no website + active on Google Maps, OR broken/unreachable site, OR site has no SSL
- **B (Warm)**: Social-only with no reviews, OR site not mobile-friendly, OR PageSpeed < 50, OR high-value industry with outdated/template site
- **C (Lukewarm)**: Template site underperforming, OR no website and no reviews
- **D (Low priority)**: Functional modern site, OR permanently closed business

## Social Media Detection
The skill automatically detects businesses that have no real website:
- **Facebook/Instagram listed as website** on Google Maps → `website_type: social_only`
- **Domain redirects to Facebook/Instagram** → caught during website crawl, reclassified as `social_only`
- Both cases are scored A (with reviews) or B (without reviews) — they are strong prospects

## Finding More No-Website Businesses
Google Places returns the most prominent results first (which tend to have websites). To surface smaller, no-website businesses:
- **Search by district** in large cities: `"fogorvos Budapest XIV. kerület"`, `"fogorvos Budapest VIII. kerület"`, etc.
- **Use broader terms**: `"rendelő"`, `"szalon"`, `"műhely"` tend to surface smaller operations
- **Run multiple queries**: combine results with `--output` to different files, then merge

## Edge Cases
- **Zero results**: Broaden query — try English synonym, remove diacritics, or use a larger region
- **80% quality check fails**: Business type may not appear in Google Maps under that query — refine
- **Evaluation slow**: Lower `--workers` (e.g., `--workers 2`) or run overnight
- **Google Places quota exceeded**: Free tier = 2,500 Text Searches/day. Upgrade project billing or wait 24h
- **Missing API keys**: See `SETUP.md` for step-by-step configuration

## Environment
Requires `.env` in the `prospect-research/` directory:
```
GOOGLE_MAPS_API_KEY=your_key
GOOGLE_APPLICATION_CREDENTIALS=path/to/credentials.json
PAGESPEED_API_KEY=your_key   # optional — raises rate limit from 1/s to higher
USER_EMAIL=your_email        # optional — shares the Sheet with you automatically
```
