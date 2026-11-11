"""Shared paths and small helpers."""
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HEADLINES = DATA / "headlines"
LABELS = DATA / "labels"
PRICES = DATA / "prices"
RESULTS = ROOT / "results"
PROMPT_VERSION = "label_v1"
PROMPT_FILE = ROOT / "prompts" / f"{PROMPT_VERSION}.txt"

# Labelling started on this date. Nothing before it is scored.
START_DATE = "2026-11-11"


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_universe():
    with open(ROOT / "universe.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def normalise_title(title):
    t = title.lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def headline_id(ticker, title):
    return hashlib.sha1(f"{ticker}|{normalise_title(title)}".encode()).hexdigest()[:12]


def read_jsonl_dir(folder):
    rows = []
    if folder.exists():
        for p in sorted(folder.glob("*.jsonl")):
            with open(p, encoding="utf-8") as f:
                rows += [json.loads(line) for line in f if line.strip()]
    return rows


def append_jsonl(folder, month, rows):
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / f"{month}.jsonl", "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
