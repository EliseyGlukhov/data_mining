import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

CLEAN = Path("clean"); CLEAN.mkdir(exist_ok=True)

THRESHOLDS = {
    "completeness_required":      (0.99, 0.95, "higher"),
    "completeness_optional":      (0.70, 0.50, "higher"),
    "uniqueness_key":             (1.00, 0.95, "higher"),
    "validity":                   (0.90, 0.80, "higher"),
    "rejection_rate":             (0.05, 0.15, "lower"),
    "business_rules_consistency": (0.98, 0.90, "higher"),
    "freshness_days":             (1.0,  7.0,  "lower"),
    "volume_stability":           (0.10, 0.30, "lower"),
}

OPTIONAL_FIELDS_BY_SOURCE = {
    "html_books_toscrape": ["price", "rating", "category", "availability"],
    "openlibrary_api":     ["author_key", "isbn", "publish_year"],
}


def classify(metric: str, value: float) -> str:
    g, y, direction = THRESHOLDS[metric]
    if direction == "higher":
        return "green" if value >= g else ("yellow" if value >= y else "red")
    return "green" if value <= g else ("yellow" if value <= y else "red")


def _optional_completeness(df: pd.DataFrame) -> float:
    scores, weights = [], []
    for src, fields in OPTIONAL_FIELDS_BY_SOURCE.items():
        sub = df[df["source"] == src]
        if sub.empty:
            continue
        present = [f for f in fields if f in sub.columns]
        if not present:
            continue
        scores.append(float(sub[present].notna().mean().mean()))
        weights.append(len(sub))
    if not weights:
        return 0.0
    total = sum(weights)
    return sum(s * w for s, w in zip(scores, weights)) / total


def metrics(prev_count: int | None = None) -> dict:
    df = pd.read_parquet(CLEAN / "dataset.parquet")

    rp = CLEAN / "rejects.jsonl"
    rejects = [json.loads(l) for l in open(rp, encoding="utf-8")] if rp.exists() else []
    raw_total = len(df) + len(rejects)

    req_cols = [c for c in ("book_key", "title", "source", "source_url") if c in df.columns]
    req_ok = float(df[req_cols].notna().all(axis=1).mean()) if len(df) else 0.0

    opt_ok = _optional_completeness(df)

    uniq = bool(df["book_key"].is_unique) and bool(df["book_key"].notna().all())
    valid = 1 - len(rejects) / max(raw_total, 1)
    rej_r = len(rejects) / max(raw_total, 1)
    rules = 1 - sum("rule" in r.get("reason", "") for r in rejects) / max(raw_total, 1)

    if "collected_at" in df.columns and len(df):
        latest = pd.to_datetime(df["collected_at"], utc=True, errors="coerce").max()
        age = (datetime.now(timezone.utc) - latest).days if pd.notna(latest) else 999
    else:
        age = 999

    vol = abs(len(df) - prev_count) / prev_count if prev_count else 0.0

    raw = {
        "completeness_required":      req_ok,
        "completeness_optional":      opt_ok,
        "uniqueness_key":             1.0 if uniq else 0.0,
        "validity":                   valid,
        "rejection_rate":             rej_r,
        "business_rules_consistency": rules,
        "freshness_days":             float(age),
        "volume_stability":           float(vol),
    }
    return {k: {"value": float(v), "status": classify(k, v)} for k, v in raw.items()}


def verdict(m: dict) -> str:
    order = {"green": 0, "yellow": 1, "red": 2}
    return max((v["status"] for v in m.values()), key=lambda s: order[s])


def should_load_mart(m: dict) -> bool:
    v = verdict(m)
    if v == "red":
        bad = [k for k, x in m.items() if x["status"] == "red"]
        print(f"[!] MART LOAD ABORTED — red metrics: {bad}")
        for k in bad:
            g, y, dirn = THRESHOLDS[k]
            print(f"   • {k} = {m[k]['value']:.4f} "
                  f"(порог yellow: {'≥' if dirn == 'higher' else '≤'} {y})")
        return False
    print(f"MART LOAD ALLOWED — verdict={v}")
    return True