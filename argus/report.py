"""Render a run into a finished, source-linked intelligence assessment (Markdown)."""
from __future__ import annotations

from .store import Store

CONF_WORDS = {"high": "High confidence", "moderate": "Moderate confidence", "low": "Low confidence"}


def _cite(store: Store, eid: str) -> str:
    ev = store.get_evidence(eid)
    if not ev:
        return eid
    url = ev["url"] or ""
    title = (ev["title"] or eid)[:90]
    return f"[{eid}]({url}) *{title}* ({ev['year']})" if url.startswith("http") else f"`{eid}` *{title}* ({ev['year']})"


def _end(t: str) -> str:
    t = t.strip()
    return t if t[-1:] in '.?!' else t + '.'


def _names(store: Store, ids: list[str]) -> str:
    return ", ".join((store.get_entity(i) or {}).get("name", i) for i in ids)


def render(store: Store) -> str:
    mission = store.get_meta("mission", "")
    summary = store.get_meta("summary", "")
    gaps = store.get_meta("collection_gaps", "")
    findings = store.findings()
    kept = [f for f in findings if f["verdict"] in ("verified", "downgraded")]
    rejected = [f for f in findings if f["verdict"] == "rejected"]
    s = store.stats()
    L = ["# ARGUS-Q Intelligence Assessment", ""]
    if store.get_meta("note"):
        L += [f"> **Note:** {store.get_meta('note')}", ""]
    L += [
         f"**Mission:** {mission}", "",
         f"*Run type: {store.get_meta('kind', '?')} · model: {store.get_meta('model', 'n/a')} · "
         f"steps: {store.get_meta('steps_used', '?')} · evidence records: {s['evidence']} · "
         f"entities: {s['entities']} · relationships: {s['relationships']}*", "",
         "## Bottom line", "", summary or "_No summary submitted._", ""]
    order = {"high": 0, "moderate": 1, "low": 2}
    kept.sort(key=lambda f: order.get(f["confidence"], 3))
    L += ["## Key judgments", ""]
    if not kept:
        L.append("_No findings passed review._")
    for n, f in enumerate(kept, 1):
        tag = CONF_WORDS.get(f["confidence"], f["confidence"])
        L += [f"### {n}. {f['statement']}", "",
              f"**{tag}** · {f['category'].replace('_', ' ')}"
              + (" · *confidence lowered in review*" if f["verdict"] == "downgraded" else ""), "",
              f"- **Entities:** {_names(store, f['entity_ids'])}",
              "- **Evidence:** " + "; ".join(_cite(store, e) for e in f["evidence_ids"])]
        if f.get("gaps"):
            L.append(f"- **What would change this:** {f['gaps']}")
        if f["verdict_notes"]:
            L.append(f"- **Reviewer notes:** {f['verdict_notes']}")
        L.append("")
    if gaps:
        L += ["## Collection gaps", "", gaps, ""]
    open_leads = [l for l in store.leads() if l["status"] == "open"]
    closed = [l for l in store.leads() if l["status"] == "closed"]
    if open_leads or closed:
        L += ["## Leads", ""]
        for l in open_leads:
            L.append(f"- **Open — {_end(l['title'])}** {l['rationale']}")
        for l in closed:
            L.append(f"- **Closed — {_end(l['title'])}** {l['outcome']}")
        L.append("")
    if rejected:
        L += ["## Claims rejected in review", "",
              "These were proposed during the investigation but failed independent checking and are excluded from the judgments above.", ""]
        for f in rejected:
            L.append(f"- ~~{f['statement']}~~ — {f['verdict_notes']}")
        L.append("")
    L += ["## Method and limits", "",
          "ARGUS-Q collected public records, built a provenance-linked graph (every relationship points to a retrieved record), "
          "and chose its own next steps. Each finding was then checked by an independent reviewer for citation validity, "
          "entity grounding, screening-match strength, identity resolution, and evidentiary support.",
          "",
          "This assessment describes documented relationships and their strategic significance. It does not allege wrongdoing by "
          "any person or organization. International research collaboration is common and lawful.", ""]
    return "\n".join(L)
