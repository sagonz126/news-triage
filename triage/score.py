"""Score the labels against what the shares actually did.

Unit of scoring: one company on one reaction day. If several relevant headlines
point at the same reaction day, the one with the largest predicted size counts
(ties: highest confidence). Headlines that already report a price move are
excluded, because they describe the outcome instead of predicting it.

Reaction day: the first trading day whose close comes after the headline was seen.

Two samples are reported:
  all        every scored company-day
  pre-close  only company-days where the label was committed before that day's close,
             so the label was a genuine forecast of the close
"""
import json
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import pandas as pd

from .baseline import label as keyword_label
from .common import HEADLINES, LABELS, PRICES, RESULTS, START_DATE, iso, load_universe, now_utc, read_jsonl_dir

SIZE_RANK = {"noise": 0, "notable": 1, "big": 2}


def actual_size(z):
    a = abs(z)
    return "noise" if a < 1 else "notable" if a < 2 else "big"


def actual_direction(z):
    return "none" if abs(z) < 1 else ("up" if z > 0 else "down")


def reaction_day(seen_utc, days, tz, close):
    local = datetime.fromisoformat(seen_utc.replace("Z", "+00:00")).astimezone(ZoneInfo(tz))
    hh, mm = map(int, close.split(":"))
    for d in days:
        dd = datetime.strptime(d, "%Y-%m-%d").date()
        if dd > local.date() or (dd == local.date() and local.time() < dtime(hh, mm)):
            close_utc = datetime.combine(dd, dtime(hh, mm), ZoneInfo(tz))
            return d, iso(close_utc)
    return None, None


def metrics(df, pred_dir, pred_size):
    n = len(df)
    if n == 0:
        return {"n": 0}
    size_hit = (df[pred_size] == df["act_size"]).mean()
    moved = df["act_size"] != "noise"
    flagged = df[pred_size] != "noise"
    precision = (moved & flagged).sum() / flagged.sum() if flagged.sum() else None
    recall = (moved & flagged).sum() / moved.sum() if moved.sum() else None
    dir_rows = df[moved & (df[pred_dir] != "none")]
    dir_hit = (dir_rows[pred_dir] == dir_rows["act_dir"]).mean() if len(dir_rows) else None
    r = lambda x: None if x is None or pd.isna(x) else round(float(x), 3)
    return {
        "n": n,
        "size_accuracy": r(size_hit),
        "move_precision": r(precision),
        "move_recall": r(recall),
        "direction_accuracy_on_moves": r(dir_hit),
        "direction_n": int(len(dir_rows)),
    }


def main():
    uni = {c["ticker"]: c for c in load_universe()}
    heads = {h["id"]: h for h in read_jsonl_dir(HEADLINES)}
    labels = read_jsonl_dir(LABELS)
    ab = pd.read_csv(PRICES / "abnormal.csv", dtype={"date": str}).dropna(subset=["z"])
    days_by = {t: sorted(g["date"]) for t, g in ab.groupby("ticker")}
    ab = ab.set_index(["ticker", "date"])

    rows = []
    for lab in labels:
        h = heads.get(lab["id"])
        if not h or h["seen_utc"][:10] < START_DATE:
            continue
        if not lab["relevant"] or lab["reports_price_move"]:
            continue
        co = uni[h["ticker"]]
        day, close_utc = reaction_day(h["seen_utc"], days_by.get(h["ticker"], []), co["tz"], co["close"])
        if day is None or (h["ticker"], day) not in ab.index:
            continue  # reaction day not traded yet
        z = float(ab.loc[(h["ticker"], day), "z"])
        kw = keyword_label(h["title"])
        rows.append({
            "id": lab["id"], "ticker": h["ticker"], "company": h["company"], "day": day,
            "title": h["title"], "seen_utc": h["seen_utc"], "labelled_utc": lab["labelled_utc"],
            "pre_close": lab["labelled_utc"] < close_utc,
            "llm_dir": lab["direction"], "llm_size": lab["size"], "conf": lab["confidence"],
            "kw_dir": kw["direction"], "kw_size": kw["size"],
            "z": round(z, 2), "act_dir": actual_direction(z), "act_size": actual_size(z),
        })

    RESULTS.mkdir(parents=True, exist_ok=True)
    out = {"updated_utc": iso(now_utc()), "start_date": START_DATE}
    if rows:
        df = pd.DataFrame(rows)
        df["rank"] = df["llm_size"].map(SIZE_RANK)
        days = (df.sort_values(["rank", "conf"], ascending=False)
                  .drop_duplicates(["ticker", "day"]).copy())
        days["none_dir"], days["none_size"] = "none", "noise"
        for name, sample in (("all", days), ("pre_close", days[days["pre_close"]])):
            out[name] = {
                "llm": metrics(sample, "llm_dir", "llm_size"),
                "keyword_baseline": metrics(sample, "kw_dir", "kw_size"),
                "always_no_move": metrics(sample, "none_dir", "none_size"),
            }
        days.drop(columns=["rank", "none_dir", "none_size"]).to_csv(RESULTS / "scored_days.csv", index=False)
        out["headlines_labelled"] = len(labels)
        out["company_days_scored"] = len(days)
    else:
        out["note"] = "No reaction days have closed yet."
    (RESULTS / "results.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
