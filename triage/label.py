"""Label every headline that has no label yet, using the Gemini API free tier.

Headlines go in batches, so a full day costs a handful of requests and stays
inside the free daily limits. Every label records the model, the prompt version
and the time it was made; the GitHub commit that adds it is the public time stamp.
"""
import json
import os
import sys
import time

import requests

from .common import HEADLINES, LABELS, PROMPT_FILE, PROMPT_VERSION, append_jsonl, iso, now_utc, read_jsonl_dir

BASE = "https://generativelanguage.googleapis.com/v1beta"
# First available model in this list is used, unless GEMINI_MODEL is set.
PREFERRED = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash"]
BATCH = 60
MAX_BATCHES_PER_RUN = 12
FIELDS = {"id", "relevant", "reports_price_move", "direction", "size", "vol_up", "confidence", "reason"}


def headers():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY is not set")
    return {"x-goog-api-key": key, "Content-Type": "application/json"}


def pick_model():
    if os.environ.get("GEMINI_MODEL"):
        return os.environ["GEMINI_MODEL"]
    r = requests.get(f"{BASE}/models", headers=headers(), params={"pageSize": 200}, timeout=30)
    r.raise_for_status()
    available = {m["name"].split("/", 1)[1] for m in r.json().get("models", [])}
    for m in PREFERRED:
        if m in available:
            return m
    sys.exit(f"None of {PREFERRED} available. Available: {sorted(available)}")


def call(model, system, payload):
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
    }
    for attempt in range(4):
        r = requests.post(f"{BASE}/models/{model}:generateContent", headers=headers(), json=body, timeout=180)
        if r.status_code == 200:
            parts = r.json()["candidates"][0]["content"]["parts"]
            return json.loads("".join(p.get("text", "") for p in parts))
        if r.status_code in (429, 500, 503):
            time.sleep(30 * (attempt + 1))
            continue
        r.raise_for_status()
    raise RuntimeError(f"gave up after retries: HTTP {r.status_code} {r.text[:200]}")


def valid(lab):
    return (
        FIELDS <= set(lab)
        and lab["direction"] in ("up", "down", "none")
        and lab["size"] in ("noise", "notable", "big")
    )


def main():
    labelled = {l["id"] for l in read_jsonl_dir(LABELS)}
    todo = [h for h in read_jsonl_dir(HEADLINES) if h["id"] not in labelled]
    if not todo:
        print("nothing to label")
        return
    model = pick_model()
    system = PROMPT_FILE.read_text(encoding="utf-8")
    print(f"{len(todo)} headlines to label with {model}")
    done = 0
    for i in range(0, min(len(todo), BATCH * MAX_BATCHES_PER_RUN), BATCH):
        chunk = todo[i:i + BATCH]
        payload = [{k: h[k] for k in ("id", "company", "title", "domain", "seen_utc")} for h in chunk]
        try:
            out = call(model, system, payload)
        except Exception as e:  # keep going; unlabelled headlines are retried next run
            print(f"  batch {i // BATCH} failed: {e}", file=sys.stderr)
            continue
        ids = {h["id"] for h in chunk}
        stamp = iso(now_utc())
        rows = []
        for lab in out if isinstance(out, list) else []:
            if isinstance(lab, dict) and valid(lab) and lab["id"] in ids:
                rows.append({**{k: lab[k] for k in FIELDS}, "model": model,
                             "prompt": PROMPT_VERSION, "labelled_utc": stamp})
        append_jsonl(LABELS, stamp[:7], rows)
        done += len(rows)
        time.sleep(5)
    print(f"labelled {done}")


if __name__ == "__main__":
    main()
