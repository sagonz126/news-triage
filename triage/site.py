"""Write the files the website reads.

results/site.json      small, loaded on every visit: totals, scorecard, bias, and an
                       index of trading days with their counts
results/feed/DAY.json  the relevant calls whose reaction day is DAY, with outcomes;
                       loaded only when a visitor opens that day
results/feed/pending.json  calls whose reaction day has not closed yet
"""
import json
from collections import Counter

import pandas as pd

from .common import canonical, HEADLINES, LABELS, PRICES, PROMPT_VERSION, RESULTS, START_DATE, iso, load_universe, now_utc, read_jsonl_dir
from .score import actual_direction, actual_size, reaction_day

FEED = RESULTS / "feed"


def hit(item):
    """Same rule as the website: a call is right if it called a move and the stock moved
    (in the called direction, if it called one), or called no move and the stock stayed quiet."""
    if "z" not in item:
        return None
    flagged, moved = item["size"] != "noise", item["act_size"] != "noise"
    if not flagged:
        return not moved
    return moved and item["dir"] in ("none", item["act_dir"])


def main():
    uni = {c["ticker"]: c for c in load_universe()}
    heads = {h["id"]: {**h, "ticker": canonical(h["ticker"])} for h in read_jsonl_dir(HEADLINES)}
    labels = [l for l in read_jsonl_dir(LABELS) if l["id"] in heads]

    ab, days_by = None, {}
    if (PRICES / "abnormal.csv").exists():
        ab = pd.read_csv(PRICES / "abnormal.csv", dtype={"date": str}).dropna(subset=["z"])
        days_by = {t: sorted(g["date"]) for t, g in ab.groupby("ticker")}
        ab = ab.set_index(["ticker", "date"])["z"]

    relevant = [l for l in labels if l["relevant"] and not l["reports_price_move"]]
    groups = {}
    for l in sorted(relevant, key=lambda l: heads[l["id"]]["seen_utc"], reverse=True):
        h = heads[l["id"]]
        if h["seen_utc"][:10] < START_DATE:
            continue
        co = uni.get(h["ticker"], {})
        item = {
            "t": h["seen_utc"], "co": h["company"], "title": h["title"], "url": h.get("url"),
            "src": h.get("domain"), "dir": l["direction"], "size": l["size"],
            "conf": l["confidence"], "why": l["reason"],
        }
        key = "pending"
        if ab is not None and co:
            day, _ = reaction_day(h["seen_utc"], days_by.get(h["ticker"], []), co["tz"], co["close"])
            if day and (h["ticker"], day) in ab.index:
                z = float(ab.loc[(h["ticker"], day)])
                item.update({"z": round(z, 2), "act_size": actual_size(z), "act_dir": actual_direction(z)})
                key = day
        groups.setdefault(key, []).append(item)

    FEED.mkdir(parents=True, exist_ok=True)
    for old in FEED.glob("*.json"):
        if old.stem not in groups:
            old.unlink()
    days = []
    for key, items in groups.items():
        (FEED / f"{key}.json").write_text(json.dumps(items, ensure_ascii=False, separators=(",", ":")))
        hits = [hit(i) for i in items]
        days.append({
            "day": key, "calls": len(items),
            "flagged": sum(1 for i in items if i["size"] != "noise"),
            "scored": sum(1 for x in hits if x is not None),
            "hits": sum(1 for x in hits if x),
        })
    days.sort(key=lambda d: "9999" if d["day"] == "pending" else d["day"], reverse=True)

    score = None
    if (RESULTS / "results.json").exists():
        score = json.loads((RESULTS / "results.json").read_text())

    actual_dirs = Counter()
    if score and (RESULTS / "scored_days.csv").exists():
        sd = pd.read_csv(RESULTS / "scored_days.csv")
        actual_dirs = Counter(sd["act_dir"])
        predicted_dirs = Counter(sd["llm_dir"])
    else:
        predicted_dirs = Counter(l["direction"] for l in relevant)

    by_day = Counter(heads[l["id"]]["seen_utc"][:10] for l in labels)
    out = {
        "updated_utc": iso(now_utc()),
        "start_date": START_DATE,
        "model": labels[-1]["model"] if labels else None,
        "prompt": PROMPT_VERSION,
        "companies": len(uni),
        "totals": {
            "headlines": len(heads),
            "labelled": len(labels),
            "relevant": len(relevant),
            "price_move_excluded": sum(1 for l in labels if l["reports_price_move"]),
            "flagged": sum(1 for l in relevant if l["size"] != "noise"),
        },
        "calls": {
            "size": dict(Counter(l["size"] for l in relevant)),
            "direction": dict(Counter(l["direction"] for l in relevant)),
        },
        "bias": {"predicted": dict(predicted_dirs), "actual": dict(actual_dirs)},
        "score": score,
        "per_day": dict(sorted(by_day.items())[-30:]),
        "per_company": dict(Counter(heads[l["id"]]["company"] for l in relevant).most_common()),
        "days": days,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "site.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"site.json: {len(days)} days, {sum(d['calls'] for d in days)} calls, "
          f"{(RESULTS / 'site.json').stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
