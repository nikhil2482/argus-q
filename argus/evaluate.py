"""Score a synthetic-world run against the answer key."""
from __future__ import annotations

from .sources.synthetic import GROUND_TRUTH
from .store import Store

LEVELS = ["low", "moderate", "high"]


def _finding_text(store: Store, f: dict) -> tuple[str, str]:
    names = " | ".join(((store.get_entity(i) or {}).get("name") or "").lower() for i in f["entity_ids"])
    return names, f["statement"].lower()


def _matches(fact: dict, names: str, stmt: str) -> bool:
    if any(n not in names for n in fact.get("names_all", [])):
        return False
    if fact.get("names_any"):
        if sum(1 for n in fact["names_any"] if n in names) < fact.get("names_any_min", 1):
            return False
    if fact.get("keywords_any") and not any(k in stmt for k in fact["keywords_any"]):
        return False
    return True


def score(store: Store, gt: dict = GROUND_TRUTH) -> dict:
    findings = store.findings()
    kept = [f for f in findings if f["verdict"] in ("verified", "downgraded")]
    texts = [(f, *_finding_text(store, f)) for f in kept]

    facts = []
    for fact in gt["facts"]:
        hit = next((f for f, n, s in texts if _matches(fact, n, s)), None)
        facts.append({"id": fact["id"], "label": fact["label"], "found": hit is not None,
                      "finding": hit["statement"] if hit else None})

    false_flags = []
    for f, names, _ in texts:
        if f["category"] != "foreign_link":
            continue
        if any(d in names for d in gt["distractors"]) and not any(c in names for c in gt["concern_entities"]):
            false_flags.append(f["statement"])

    overclaims = []
    for f, names, _ in texts:
        for oc in gt["overclaims"]:
            if all(n in names for n in oc["names_all"]) and \
                    LEVELS.index(f["confidence"]) > LEVELS.index(oc["max_confidence"]):
                overclaims.append(f["statement"])

    found = sum(x["found"] for x in facts)
    return {
        "fact_recall": round(found / len(facts), 2),
        "facts_found": f"{found}/{len(facts)}",
        "false_flags": len(false_flags),
        "overclaims": len(overclaims),
        "findings_submitted": len(findings),
        "findings_kept": len(kept),
        "findings_rejected_by_skeptic": len(findings) - len(kept),
        "steps": store.get_meta("steps_used"),
        "evidence_records": store.stats()["evidence"],
        "facts": facts,
        "false_flag_examples": false_flags[:5],
        "overclaim_examples": overclaims,
    }
