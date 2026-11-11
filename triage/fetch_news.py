"""Fetch new English headlines for every company.

Two free sources, merged:
  1. Google News RSS search, one query per company (main source: broad and timely).
  2. Yahoo Finance news for the ticker (second source: already tagged to the stock).

GDELT was the first choice but rate-limits GitHub's shared servers (HTTP 429 on
almost every request on 11 Nov 2026), so it was dropped.

We keep anything published in the last LOOKBACK_HOURS that we do not already have
(same company, same normalised title) and append it to data/headlines/YYYY-MM.jsonl.
"""
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests
import yfinance as yf

from .common import HEADLINES, append_jsonl, headline_id, iso, load_universe, normalise_title, now_utc, read_jsonl_dir

GOOGLE = "https://news.google.com/rss/search"
LOOKBACK_HOURS = 30     # runs every 6 hours; generous overlap, duplicates are dropped
PAUSE_SECONDS = 2
UA = {"User-Agent": "Mozilla/5.0 (news-triage research project; github.com/sagonz126/news-triage)"}


def google_news(query):
    params = {"q": f"{query} when:2d", "hl": "en-GB", "gl": "GB", "ceid": "GB:en"}
    r = requests.get(GOOGLE, params=params, headers=UA, timeout=30)
    r.raise_for_status()
    out = []
    for it in ET.fromstring(r.content).findall(".//item"):
        title = it.findtext("title") or ""
        source = it.findtext("source") or ""
        # Google appends " - Source" to every title; strip it
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        out.append({
            "title": title.strip(),
            "source": source,
            "url": it.findtext("link"),
            "published": parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc),
            "via": "google_news",
        })
    return out


def yahoo_news(ticker):
    out = []
    for a in yf.Ticker(ticker).news or []:
        c = a.get("content", a)
        pub = c.get("pubDate")
        if not pub or not c.get("title"):
            continue
        out.append({
            "title": c["title"].strip(),
            "source": (c.get("provider") or {}).get("displayName", ""),
            "url": ((c.get("canonicalUrl") or {}).get("url")) or "",
            "published": datetime.fromisoformat(pub.replace("Z", "+00:00")),
            "via": "yahoo",
        })
    return out


def main():
    seen = {h["id"] for h in read_jsonl_dir(HEADLINES)}
    now = now_utc()
    cutoff = now - timedelta(hours=LOOKBACK_HOURS)
    new_rows, failures = [], []
    for co in load_universe():
        items = []
        for name, fn, arg in (("google", google_news, co["query"]), ("yahoo", yahoo_news, co["ticker"])):
            try:
                items += fn(arg)
            except Exception as e:  # one failing source must not stop the run
                failures.append(f"{co['name']} ({name}): {repr(e)[:120]}")
            time.sleep(PAUSE_SECONDS)
        for a in items:
            if a["published"] < cutoff or len(normalise_title(a["title"])) < 15:
                continue
            hid = headline_id(co["ticker"], a["title"])
            if hid in seen:
                continue
            seen.add(hid)
            new_rows.append({
                "id": hid,
                "company": co["name"],
                "ticker": co["ticker"],
                "title": a["title"],
                "domain": a["source"],
                "url": a["url"],
                "via": a["via"],
                "seen_utc": iso(a["published"]),
                "fetched_utc": iso(now),
            })
    append_jsonl(HEADLINES, iso(now)[:7], new_rows)
    print(f"{len(new_rows)} new headlines; {len(failures)} source failures")
    for f in failures:
        print("  " + f, file=sys.stderr)


if __name__ == "__main__":
    main()
