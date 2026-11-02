"""Non-agentic baseline: a fixed list of searches plus rule-based flagging.

This is what a careful script (no judgment, no lead-following) produces. The
evaluation compares ARGUS-Q against it to show whether autonomous planning adds
measurable value.
"""
from __future__ import annotations

from .screening import Screener
from .skeptic import review
from .store import Store
from .tools import Toolkit

FIXED_QUERIES = ["superconducting qubit", "dilution refrigerator", "quantum computing",
                 "quantum processor", "qubit readout"]


def run_baseline(store: Store, source, screener: Screener, queries: list[str] = FIXED_QUERIES) -> dict:
    tk = Toolkit(store, source, screener)
    tk.max_steps = 999
    store.set_meta("kind", "baseline")
    store.set_meta("mission", "Fixed-search baseline: " + ", ".join(queries))
    step = 0
    for q in queries:
        step += 1
        _, s = tk.call("search_publications", {"query": q, "limit": 10})
        store.log_decision(step, "search_publications", {"query": q}, "fixed query", s)
        if getattr(source, "patents_enabled", False):
            step += 1
            _, s = tk.call("search_patents", {"query": q, "limit": 10})
            store.log_decision(step, "search_patents", {"query": q}, "fixed query", s)

    orgs = [e for e in store.all_entities() if e["kind"] == "organization"]
    for o in orgs:
        if o["country"] and o["country"] != "US":
            tk.call("screen_entity", {"entity_id": o["id"]})

    findings = []
    us = {o["id"] for o in orgs if o["country"] == "US"}
    # Rule 1: any screening hit (any strength) is reported.
    for o in (store.get_entity(x["id"]) for x in orgs):
        hits = o["attrs"].get("screening") or []
        if hits:
            rels = store.relationships_for(o["id"], 200)
            ev = sorted({r["evidence_id"] for r in rels})[:4]
            ents = {o["id"]}
            for e in ev:
                ents.update(store.entities_for_evidence(e))
            findings.append({"statement": f"{o['name']} matches the screening list entry '{hits[0]['listed_name']}' "
                                          f"(score {hits[0]['score']}) and appears in records with U.S. organizations.",
                             "category": "foreign_link", "confidence": "moderate",
                             "evidence_ids": ev, "entity_ids": sorted(ents), "gaps": "rule-based"})
    # Rule 2: every US-foreign co-publication is reported as a foreign link.
    for r in store.all_relationships():
        if r["rel_type"] != "CO_PUBLISHED_WITH":
            continue
        a, b = store.get_entity(r["src"]), store.get_entity(r["dst"])
        pair = {a["id"], b["id"]}
        if pair & us and any(x["country"] not in (None, "US") for x in (a, b)):
            findings.append({"statement": f"{a['name']} ({a['country']}) co-published with {b['name']} ({b['country']}).",
                             "category": "foreign_link", "confidence": "moderate",
                             "evidence_ids": [r["evidence_id"]], "entity_ids": sorted(pair), "gaps": "rule-based"})
    reviewed = review(findings, store)
    store.save_findings(reviewed)
    store.set_meta("summary", f"Baseline ran {len(queries)} fixed queries and produced {len(reviewed)} rule-based flags.")
    store.set_meta("steps_used", step)
    return {"findings": reviewed, "stats": store.stats()}
