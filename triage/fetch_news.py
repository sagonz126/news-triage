"""Fetch new English headlines for every company from the GDELT DOC 2.0 API.

GDELT is a free, open index of world news. We ask for articles seen in the last
`LOOKBACK_HOURS`, drop anything we already have (same company, same normalised
title), and append the rest to data/headlines/YYYY-MM.jsonl.
"""
import json
import sys
import time
from datetime import datetime, timezone

import requests

from .common import HEADLINES, append_jsonl, headline_id, iso, load_universe, normalise_title, now_utc, read_jsonl_dir

API = "https://api.gdeltproject.org/api/v2/doc/doc"
LOOKBACK_HOURS = 8      # runs every 6 hours, so windows overlap a little
MAX_RECORDS = 75
PAUSE_SECONDS = 6       # GDELT asks for at most one request every 5 seconds


def fetch(query):
    params = {
        "query": f"{query} sourcelang:english",
        "mode": "artlist",
        "format": "json",
        "maxrecords": MAX_RECORDS,
        "timespan": f"{LOOKBACK_HOURS}h",
        "sort": "datedesc",
    }
    for attempt in range(3):
        r = requests.get(API, params=params, timeout=60)
        if r.status_code == 200:
            try:
                return r.json().get("articles", [])
            except json.JSONDecodeError:
                # GDELT answers some malformed queries with plain text
                print(f"  not JSON for {query!r}: {r.text[:120]}", file=sys.stderr)
                return []
        time.sleep(PAUSE_SECONDS * (attempt + 2))
    print(f"  failed {query!r}: HTTP {r.status_code}", file=sys.stderr)
    return []


def main():
    seen = {h["id"] for h in read_jsonl_dir(HEADLINES)}
    fetched_at = iso(now_utc())
    new_rows, errors = [], 0
    for co in load_universe():
        try:
            arts = fetch(co["query"])
        except requests.RequestException as e:
            print(f"  error {co['name']}: {e}", file=sys.stderr)
            arts, errors = [], errors + 1
        for a in arts:
            title = (a.get("title") or "").strip()
            if len(normalise_title(title)) < 15:
                continue
            hid = headline_id(co["ticker"], title)
            if hid in seen:
                continue
            seen.add(hid)
            seen_dt = datetime.strptime(a["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            new_rows.append({
                "id": hid,
                "company": co["name"],
                "ticker": co["ticker"],
                "title": title,
                "domain": a.get("domain"),
                "url": a.get("url"),
                "seen_utc": iso(seen_dt),
                "fetched_utc": fetched_at,
            })
        time.sleep(PAUSE_SECONDS)
    month = fetched_at[:7]
    append_jsonl(HEADLINES, month, new_rows)
    print(f"{len(new_rows)} new headlines, {errors} companies failed")


if __name__ == "__main__":
    main()
