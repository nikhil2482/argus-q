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
NEGATION = re.compile(r"\b(not|no|none|neither|nor|never|without|weak|isn't|aren't|wasn't|absent)\b", re.I)


def asserts_listing(statement: str) -> bool:
    """True if some sentence says an entity IS listed or sanctioned. Sentences
    that deny a listing ("none of them are on the list") or describe a weak
    match do not count."""
    for sentence in re.split(r"(?<=[.!?;])\s+", statement or ""):
        if LISTING_CLAIM.search(sentence) and not NEGATION.search(sentence):
            return True
    return False


def _down(conf: str) -> str:
    i = LEVELS.index(conf) if conf in LEVELS else 0
    return LEVELS[max(i - 1, 0)]


ORG_FILLER = {"university", "laboratory", "lab", "institute", "college", "systems", "inc", "corp", "co", "ltd", "of", "the"}


def _name_keys(store: Store) -> dict[str, set[str]]:
    """Map each way an entity is likely to be written in prose to the entity ids
    it could mean. People: full name only. Organizations: also a short form
    ("Pell Valley" for Pell Valley Quantum Laboratory, "Northgate" for Northgate
    University). A short form shared by differently named organizations is dropped
    ("Eastern Institute" could be either institute)."""
    keys: dict[str, set[str]] = {}
    owners: dict[str, set[str]] = {}
    for e in store.all_entities():
        full = _norm(e["name"])
        if len(full) < 5:
            continue
        cands = {full}
        toks = full.split()
        if e["kind"] == "organization":
            if len(toks) >= 3:
                cands.add(" ".join(toks[:2]))
            if len(toks[0]) >= 7 and toks[0] not in ORG_FILLER:
                cands.add(toks[0])
        for c in cands:
            keys.setdefault(c, set()).add(e["id"])
            owners.setdefault(c, set()).add(full)
    return {k: v for k, v in keys.items() if len(owners[k]) == 1 or k in owners[k]}


def attach_named_entities(f: dict, store: Store) -> tuple[list[str], list[str]]:
    """Entity ids the statement names that are also named in the cited evidence. A name
    found only inside a longer matched name ("Institute of Physics" inside "Moscow
    Institute of Physics and Technology") does not count."""
    text = f" {_norm(f.get('statement', ''))} "
    hays = [store.evidence_haystack(e) for e in f.get("evidence_ids") or []]
    have = set(f.get("entity_ids") or [])
    keys = _name_keys(store)
    spans = []
    for key in keys:
        start = text.find(f" {key} ")
        while start != -1:
            spans.append((start, start + len(key) + 2, key))
            start = text.find(f" {key} ", start + 1)
    spans.sort(key=lambda s: -(s[1] - s[0]))
    kept: list[tuple[int, int, str]] = []
    for a, b, key in spans:
        if not any(a >= ka and b <= kb for ka, kb, _ in kept):
            kept.append((a, b, key))
    added, names = [], []
    for _, _, key in kept:
        for eid in sorted(keys[key]):
            e = store.get_entity(eid)
            if eid in have or not e or not any(grounded(e["name"], h) for h in hays):
                continue
            have.add(eid)
            added.append(eid)
            names.append(e["name"])
    return added, names


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

    added, added_names = attach_named_entities({**f, "evidence_ids": ev_ids}, store)
    if added:
        f["entity_ids"] = list(f.get("entity_ids") or []) + added
        notes.append(f"added entities named in the statement: {added_names}")

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

    if asserts_listing(f.get("statement", "")):
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

Call the record_verdict tool exactly once with your judgment."""

VERDICT_TOOL = {
    "name": "record_verdict",
    "strict": True,
    "description": "Record whether the evidence supports the statement.",
    "input_schema": {"type": "object", "properties": {
        "support": {"type": "string", "enum": ["supported", "partial", "unsupported"]},
        "reason": {"type": "string", "description": "One sentence."}},
        "required": ["support", "reason"], "additionalProperties": False},
}


def llm_check(f: dict, store: Store, client, model: str, usage=None) -> dict:
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
        # Forced tool_choice is rejected by Claude Sonnet 5.5, so the tool is offered with
        # tool_choice "auto" and marked strict, and the prompt asks for it.
        resp = client.messages.create(
            model=model, max_tokens=3000, tools=[VERDICT_TOOL],
            messages=[{"role": "user", "content": LLM_PROMPT.format(
                statement=f["statement"], confidence=f["confidence"], evidence="\n\n".join(blocks))}])
        if usage is not None:
            usage.add(resp)
        data = next((b.input for b in resp.content if getattr(b, "type", "") == "tool_use"), None)
        if data is None:  # fall back to JSON in text
            text = "".join(getattr(b, "text", "") for b in resp.content)
            data = json.loads(text[text.find("{"): text.rfind("}") + 1])
    except Exception as e:  # never let the reviewer crash the run
        detail = str(e).replace("\n", " ")[:160]
        f["verdict_notes"] = (f["verdict_notes"] + f"; LLM review unavailable ({type(e).__name__}: {detail})").strip("; ")
        return f
    support, reason = data.get("support"), data.get("reason", "")
    if support == "unsupported":
        f["verdict"], f["verdict_notes"] = "rejected", (f["verdict_notes"] + f"; reviewer: {reason}").strip("; ")
    elif support == "partial":
        f["confidence"] = _down(f["confidence"])
        f["verdict"] = "downgraded"
        f["verdict_notes"] = (f["verdict_notes"] + f"; reviewer (partial support): {reason}").strip("; ")
    return f


def review(findings: list[dict], store: Store, client=None, model: str | None = None, usage=None) -> list[dict]:
    out = []
    for f in findings:
        r = check_finding(f, store)
        if client is not None and model:
            r = llm_check(r, store, client, model, usage)
        out.append(r)
    return out
