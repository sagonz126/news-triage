"""Write results/site.json: one small file the website reads to show live numbers.

Kept small on purpose (the browser downloads it on every visit): totals, the
scorecard from results.json, the model's call mix against what happened, and the
latest relevant calls with their outcome where the reaction day has closed.
"""
import json
from collections import Counter

import pandas as pd

from .common import canonical, HEADLINES, LABELS, PRICES, PROMPT_VERSION, RESULTS, START_DATE, iso, load_universe, now_utc, read_jsonl_dir
from .score import actual_direction, actual_size, reaction_day

FEED_SIZE = 200


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
    feed = []
    for l in sorted(relevant, key=lambda l: heads[l["id"]]["seen_utc"], reverse=True)[:FEED_SIZE]:
        h = heads[l["id"]]
        co = uni.get(h["ticker"], {})
        item = {
            "t": h["seen_utc"], "co": h["company"], "title": h["title"], "url": h.get("url"),
            "src": h.get("domain"), "dir": l["direction"], "size": l["size"],
            "conf": l["confidence"], "why": l["reason"],
        }
        if ab is not None and co and h["seen_utc"][:10] >= START_DATE:
            day, _ = reaction_day(h["seen_utc"], days_by.get(h["ticker"], []), co["tz"], co["close"])
            if day and (h["ticker"], day) in ab.index:
                z = float(ab.loc[(h["ticker"], day)])
                item.update({"day": day, "z": round(z, 2), "act_size": actual_size(z), "act_dir": actual_direction(z)})
        feed.append(item)

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
        "feed": feed,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "site.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"site.json: {len(feed)} feed items, {(RESULTS / 'site.json').stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
