"""Name screening against a restricted-party list.

Live mode reads a CSV export of the U.S. Consolidated Screening List
(trade.gov) placed at data/consolidated_screening_list.csv. Synthetic mode uses
the fictional list bundled with the test world.

A fuzzy name match is a LEAD, never a conclusion. The score and match type are
returned so the agent (and the skeptic) can reason about it.
"""
from __future__ import annotations

import csv
import re
from difflib import SequenceMatcher
from pathlib import Path

GENERIC = {"co", "ltd", "inc", "llc", "corp", "corporation", "company", "limited", "the", "of", "gmbh", "oy", "sa"}


def _norm(name: str) -> str:
    toks = [t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if t and t not in GENERIC]
    return " ".join(toks)


class Screener:
    def __init__(self, entries: list[dict]):
        self.entries = []
        for e in entries:
            names = [e["name"]] + [n.strip() for n in (e.get("alt_names") or "").split(";") if n.strip()]
            for n in names:
                self.entries.append({**e, "matched_name": n, "_norm": _norm(n)})

    @classmethod
    def for_mode(cls, mode: str, csv_path: str | Path = "data/consolidated_screening_list.csv") -> "Screener":
        if mode == "synthetic":
            from .sources.synthetic import SCREENING_LIST
            return cls(SCREENING_LIST)
        p = Path(csv_path)
        if not p.exists():
            return cls([])
        with p.open(newline="", encoding="utf-8", errors="replace") as f:
            rows = [r for r in csv.DictReader(f) if r.get("name")]
        return cls([{"name": r["name"], "alt_names": r.get("alt_names", ""), "source": r.get("source", ""),
                     "country": r.get("country") or r.get("addresses", "")[:60]} for r in rows])

    @property
    def loaded(self) -> bool:
        return bool(self.entries)

    def screen(self, name: str, threshold: float = 0.75) -> list[dict]:
        q = _norm(name)
        if not q:
            return []
        out = []
        for e in self.entries:
            score = SequenceMatcher(None, q, e["_norm"]).ratio()
            if score >= threshold:
                kind = "exact" if q == e["_norm"] else ("strong" if score >= 0.93 else "weak")
                out.append({"listed_name": e["matched_name"], "list": e.get("source"), "country": e.get("country"),
                            "score": round(score, 3), "match": kind})
        out.sort(key=lambda x: -x["score"])
        return out[:5]
