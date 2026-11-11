"""A deliberately simple keyword baseline. The LLM has to beat this to be worth anything.

Direction is the sign of (positive words minus negative words). Any keyword hit
means "notable", no hit means "noise". The lists were written once, before any
scoring, and are not tuned on results.
"""
import re

POSITIVE = {
    "beat", "beats", "raise", "raises", "raised", "upgrade", "upgrades", "upgraded",
    "record", "surge", "surges", "soar", "soars", "jump", "jumps", "win", "wins", "won",
    "approval", "approved", "buyback", "outperform", "strong", "stronger", "boost",
    "boosts", "rebound", "rebounds", "exceeds", "tops", "higher",
}
NEGATIVE = {
    "miss", "misses", "missed", "cut", "cuts", "lower", "lowers", "lowered", "downgrade",
    "downgrades", "downgraded", "warning", "warns", "warn", "probe", "investigation",
    "fine", "fined", "recall", "lawsuit", "sued", "strike", "plunge", "plunges", "slump",
    "slumps", "fall", "falls", "weak", "weaker", "loss", "losses", "resigns", "layoffs",
    "job cuts", "halt", "halts", "delay", "delays",
}


def label(title):
    words = re.findall(r"[a-z]+", title.lower())
    text = " ".join(words)
    pos = sum(w in POSITIVE for w in words)
    neg = sum(w in NEGATIVE for w in words) + text.count("job cuts")
    if pos == neg == 0:
        return {"direction": "none", "size": "noise"}
    direction = "up" if pos > neg else "down" if neg > pos else "none"
    return {"direction": direction, "size": "notable"}
