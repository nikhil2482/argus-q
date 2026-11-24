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


# Words too common in institution names to count as evidence that two names refer to the same body.
COMMON = {"university", "institute", "technology", "laboratory", "lab", "academy", "science", "sciences",
          "research", "center", "centre", "national", "state", "and", "for", "electronic", "engineering",
          "college", "school", "group", "international", "industrial", "industry", "development"}


def _distinct(norm: str) -> set[str]:
    return {t for t in norm.split() if t not in COMMON and len(t) > 2}


def _norm(name: str) -> str:
    # Drop parenthetical qualifiers: OpenAlex writes "QuantumCTek (China)", the list writes
    # "National University of Defense Technology (NUDT)".
    name = re.sub(r"\([^)]*\)", " ", name or "")
    toks = [t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if t and t not in GENERIC]
    return " ".join(toks)


def _country(addresses: str) -> str:
    """Country code from the first address, which the list ends with ', CN' style codes."""
    first = (addresses or "").split(";")[0].strip()
    m = re.search(r",\s*([A-Z]{2})$", first)
    return m.group(1) if m else ""


class Screener:
    def __init__(self, entries: list[dict]):
        self.entries = []
        for e in entries:
            names = [e["name"]] + [n.strip() for n in (e.get("alt_names") or "").split(";") if n.strip()]
            for n in names:
                head = n.split(",", 1)[0] if "," in n else ""
                self.entries.append({**e, "matched_name": n, "_norm": _norm(n), "_head": _norm(head) if head else ""})

    @classmethod
    def for_mode(cls, mode: str, csv_path: str | Path = "data/consolidated_screening_list.csv") -> "Screener":
        if mode == "synthetic":
            from .sources.synthetic import SCREENING_LIST
            return cls(SCREENING_LIST)
        p = Path(csv_path)
        if not p.exists():
            return cls([])
        # Some entries carry addresses over 2 MB long, beyond the csv module's default limit.
        csv.field_size_limit(2**31 - 1)
        entries = []
        with p.open(newline="", encoding="utf-8", errors="replace") as f:
            for r in csv.DictReader(f):
                # Only organizations are screened, so skip people, vessels and aircraft.
                if not r.get("name") or r.get("type") in ("Individual", "Vessel", "Aircraft"):
                    continue
                entries.append({"name": r["name"], "alt_names": r.get("alt_names", ""),
                                "source": r.get("source", ""), "country": _country(r.get("addresses", ""))})
        return cls(entries)

    @property
    def loaded(self) -> bool:
        return bool(self.entries)

    def screen(self, name: str, threshold: float = 0.75) -> list[dict]:
        q = _norm(name)
        if not q:
            return []
        sm = SequenceMatcher(None, "", q)  # q is cached as the second sequence
        out = []
        for e in self.entries:
            # "P.L. KAPITZA INSTITUTE FOR PHYSICAL PROBLEMS, RUSSIAN ACADEMY OF SCIENCES": the part before
            # the comma is exactly the queried name. That usually means this body is listed with its parent
            # added, but some entries list a sub-unit of the queried body instead, so it is flagged for review.
            if e["_head"] and e["_head"] == q and e["_norm"] != q:
                out.append({"listed_name": e["matched_name"], "list": e.get("source"), "country": e.get("country"),
                            "score": 1.0, "match": "partial",
                            "note": "listed entry starts with this exact name; check whether the full entry is this body"})
            sm.set_seq1(e["_norm"])
            # cheap upper bounds first: the real list has tens of thousands of names
            if sm.real_quick_ratio() < threshold or sm.quick_ratio() < threshold:
                continue
            score = sm.ratio()
            if score >= threshold and score < 0.93 and not (_distinct(q) & _distinct(e["_norm"])):
                continue  # similar only in generic words, e.g. "Tsinghua University" vs "Sichuan University"
            if score >= threshold:
                if q == e["_norm"]:
                    kind = "exact"
                elif score >= 0.93 and _distinct(q) == _distinct(e["_norm"]):
                    kind = "strong"  # same distinctive words, small spelling differences
                else:
                    kind = "weak"    # e.g. "Core Electronics Technology Research Institute" vs "Electronic Technology Research Institute"
                out.append({"listed_name": e["matched_name"], "list": e.get("source"), "country": e.get("country"),
                            "score": round(score, 3), "match": kind})
        rank = {"exact": 0, "strong": 1, "partial": 2, "weak": 3}
        seen, uniq = set(), []
        for m in sorted(out, key=lambda x: (rank[x["match"]], -x["score"])):
            if m["listed_name"] not in seen:
                seen.add(m["listed_name"])
                uniq.append(m)
        out = uniq
        return out[:5]
