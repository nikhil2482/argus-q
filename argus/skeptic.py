"""The skeptic: an independent check on every finding before it reaches the report.

Deterministic checks run always. An optional LLM check asks a separate model
call, which sees only the statement and the cited evidence (not the agent's
reasoning), whether the evidence supports the statement.
"""
from __future__ import annotations

import json
import re

from .screening import _norm
from .store import Store
from .tools import grounded

LEVELS = ["low", "moderate", "high"]
LISTING_CLAIM = re.compile(r"\b(entity list|screening list|restricted[- ]party|listed|sanction\w*|designated)\b", re.I)


def _down(conf: str) -> str:
    i = LEVELS.index(conf) if conf in LEVELS else 0
    return LEVELS[max(i - 1, 0)]


def check_finding(f: dict, store: Store) -> dict:
    f = {**f}
    notes: list[str] = []
    verdict = "verified"
    conf = f.get("confidence", "low") if f.get("confidence") in LEVELS else "low"

    ev_ids = list(dict.fromkeys(f.get("evidence_ids") or []))
    unknown_ev = [e for e in ev_ids if not store.get_evidence(e)]
    if not ev_ids:
        return {**f, "verdict": "rejected", "verdict_notes": "cites no evidence"}
    if unknown_ev:
        return {**f, "verdict": "rejected", "verdict_notes": f"cites evidence never retrieved: {unknown_ev}"}

    ents = []
    for eid in dict.fromkeys(f.get("entity_ids") or []):
        e = store.get_entity(eid)
        if e is None:
            notes.append(f"dropped unknown entity id {eid}")
        else:
            ents.append(e)
    f["entity_ids"] = [e["id"] for e in ents]
    if not ents and f.get("category") != "context":
        return {**f, "verdict": "rejected", "verdict_notes": "; ".join(notes + ["no valid entities"])}

    hays = {e: store.evidence_haystack(e) for e in ev_ids}
    ungrounded = [e["name"] for e in ents if not any(grounded(e["name"], h) for h in hays.values())]
    if ungrounded:
        return {**f, "verdict": "rejected",
                "verdict_notes": "; ".join(notes + [f"entities not named in cited evidence: {ungrounded}"])}

    if LISTING_CLAIM.search(f.get("statement", "")):
        confirmed = [e for e in ents if any(m.get("match") in ("exact", "strong") for m in e["attrs"].get("screening", []))]
        if not confirmed:
            return {**f, "verdict": "rejected",
                    "verdict_notes": "; ".join(notes + ["asserts a listing/sanction not confirmed by an exact or strong screening match"])}

    persons = [e for e in ents if e["kind"] == "person"]
    seen: dict[str, str] = {}
    for p in persons:
        key = _norm(p["name"])
        if key in seen and seen[key] != p["id"]:
            if conf != "low":
                conf = "low"
                verdict = "downgraded"
                notes.append(f"'{p['name']}' appears as separate records; identity not resolved, confidence set to low")
        seen[key] = p["id"]

    if conf == "high" and len(ev_ids) < 2:
        conf, verdict = "moderate", "downgraded"
        notes.append("high confidence requires at least two independent evidence records")

    f["confidence"] = conf
    f["verdict"] = verdict
    f["verdict_notes"] = "; ".join(notes)
    return f


LLM_PROMPT = """You are a skeptical reviewer of intelligence findings. Judge ONLY whether the evidence below supports the statement. Ignore anything you know from outside the evidence.

STATEMENT: {statement}
CLAIMED CONFIDENCE: {confidence}

EVIDENCE:
{evidence}

Respond with JSON only: {{"support": "supported" | "partial" | "unsupported", "reason": "<one sentence>"}}"""


def llm_check(f: dict, store: Store, client, model: str) -> dict:
    if f["verdict"] == "rejected":
        return f
    blocks = []
    for eid in f["evidence_ids"][:6]:
        ev = json.loads(store.get_evidence(eid)["raw"])
        names = [f"{a['name']} ({', '.join(i['name'] for i in a.get('institutions', []))})" for a in ev.get("authors", [])]
        names += [f"assignee: {a['name']}" for a in ev.get("assignees", [])]
        names += [f"inventor: {a['name']}" for a in ev.get("inventors", [])]
        blocks.append(f"[{eid}] {ev['title']} ({ev.get('year')})\nPeople/orgs: {'; '.join(names)}\n{(ev.get('text') or '')[:1500]}")
    for e in (store.get_entity(x) for x in f["entity_ids"]):
        if e and e["attrs"].get("screening"):
            blocks.append(f"[screening result for {e['name']}] {json.dumps(e['attrs']['screening'])}")
    try:
        resp = client.messages.create(model=model, max_tokens=300, messages=[{"role": "user", "content": LLM_PROMPT.format(
            statement=f["statement"], confidence=f["confidence"], evidence="\n\n".join(blocks))}])
        text = "".join(getattr(b, "text", "") for b in resp.content)
        data = json.loads(text[text.find("{"): text.rfind("}") + 1])
    except Exception as e:  # never let the reviewer crash the run
        f["verdict_notes"] = (f["verdict_notes"] + f"; LLM review unavailable ({type(e).__name__})").strip("; ")
        return f
    support, reason = data.get("support"), data.get("reason", "")
    if support == "unsupported":
        f["verdict"], f["verdict_notes"] = "rejected", (f["verdict_notes"] + f"; reviewer: {reason}").strip("; ")
    elif support == "partial":
        f["confidence"] = _down(f["confidence"])
        f["verdict"] = "downgraded"
        f["verdict_notes"] = (f["verdict_notes"] + f"; reviewer (partial support): {reason}").strip("; ")
    return f


def review(findings: list[dict], store: Store, client=None, model: str | None = None) -> list[dict]:
    out = []
    for f in findings:
        r = check_finding(f, store)
        if client is not None and model:
            r = llm_check(r, store, client, model)
        out.append(r)
    return out
