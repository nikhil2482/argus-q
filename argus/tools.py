"""The tools the investigator agent can call. Every tool takes a `reasoning`
argument, which is written to the decision log: that log is how ARGUS-Q answers
"why did you investigate that next?"
"""
from __future__ import annotations

import json
from typing import Any

from .screening import Screener, _norm
from .store import Store, slug

REL_TYPES = ["SUPPLIES", "DEPENDS_ON", "COLLABORATES_WITH", "AFFILIATED_WITH", "DEVELOPS",
             "USES", "FUNDS", "OWNS", "BUILDS_ON_WORK_OF"]
CATEGORIES = ["dependency", "foreign_link", "capability", "gap", "context"]
CONFIDENCE = ["low", "moderate", "high"]

_R = {"reasoning": {"type": "string", "description": "Why you are taking this action now and what you expect to learn."}}


def _schema(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": {**props, **_R}, "required": required + ["reasoning"]}


TOOL_SCHEMAS: list[dict] = [
    {"name": "search_publications",
     "description": "Search scholarly publications. Results are stored as evidence; authors, institutions, "
                    "affiliations and co-publication links are added to the graph automatically.",
     "input_schema": _schema({"query": {"type": "string"}, "limit": {"type": "integer", "default": 10}}, ["query"])},
    {"name": "search_patents",
     "description": "Search patents. Assignees and inventors are added to the graph automatically. "
                    "Inventor identities are scoped to each patent: the same name on two records is NOT proof of the same person.",
     "input_schema": _schema({"query": {"type": "string"}, "limit": {"type": "integer", "default": 10}}, ["query"])},
    {"name": "expand_entity",
     "description": "Retrieve more publications for a known person or organization (by entity id) to follow a lead.",
     "input_schema": _schema({"entity_id": {"type": "string"}, "limit": {"type": "integer", "default": 15}}, ["entity_id"])},
    {"name": "get_entity",
     "description": "Show what the graph already knows about an entity: attributes, screening result, relationships and their evidence ids.",
     "input_schema": _schema({"entity_id": {"type": "string"}}, ["entity_id"])},
    {"name": "find_entities",
     "description": "Find entities already in the graph by name fragment.",
     "input_schema": _schema({"name": {"type": "string"}}, ["name"])},
    {"name": "read_evidence",
     "description": "Read the full text and metadata of one evidence record.",
     "input_schema": _schema({"evidence_id": {"type": "string"}}, ["evidence_id"])},
    {"name": "screen_entity",
     "description": "Screen an organization's name against the restricted-party list. Returns fuzzy matches with "
                    "scores. Only 'exact' or 'strong' matches can support a statement that an entity is listed; "
                    "a 'weak' match is a similarly named different entity until proven otherwise.",
     "input_schema": _schema({"entity_id": {"type": "string"}}, ["entity_id"])},
    {"name": "register_entity",
     "description": "Add an entity that appears in an evidence record's text but is not yet in the graph "
                    "(e.g. a supplier named in an abstract). Rejected unless the name appears in that evidence.",
     "input_schema": _schema({"name": {"type": "string"}, "kind": {"type": "string", "enum": ["organization", "person", "technology"]},
                              "country": {"type": "string", "description": "ISO-2 code if stated in evidence, else omit"},
                              "evidence_id": {"type": "string"}}, ["name", "kind", "evidence_id"])},
    {"name": "add_relationship",
     "description": "Record an analytic relationship between two entities. Rejected unless both entities are named in the cited evidence.",
     "input_schema": _schema({"src_id": {"type": "string"}, "dst_id": {"type": "string"},
                              "rel_type": {"type": "string", "enum": REL_TYPES},
                              "evidence_id": {"type": "string"},
                              "rationale": {"type": "string", "description": "The specific sentence or fact in the evidence that supports this."}},
                             ["src_id", "dst_id", "rel_type", "evidence_id", "rationale"])},
    {"name": "record_lead",
     "description": "Open a lead: a question worth pursuing that is not yet supported by evidence.",
     "input_schema": _schema({"title": {"type": "string"}, "rationale": {"type": "string"},
                              "entity_ids": {"type": "array", "items": {"type": "string"}}}, ["title", "rationale"])},
    {"name": "close_lead",
     "description": "Close a lead with its outcome (confirmed, refuted, or unresolved and why).",
     "input_schema": _schema({"lead_id": {"type": "integer"}, "outcome": {"type": "string"}}, ["lead_id", "outcome"])},
    {"name": "get_status",
     "description": "Summarize the investigation so far: counts, open leads, most connected organizations, foreign organizations seen.",
     "input_schema": _schema({}, [])},
    {"name": "submit_findings",
     "description": "Finish the investigation and submit the assessment. Each finding must cite evidence ids and entity ids. "
                    "Findings are independently checked; unsupported ones are rejected.",
     "input_schema": _schema({
         "summary": {"type": "string", "description": "Bottom line up front, 2-4 sentences."},
         "findings": {"type": "array", "items": {"type": "object", "properties": {
             "statement": {"type": "string"},
             "category": {"type": "string", "enum": CATEGORIES},
             "confidence": {"type": "string", "enum": CONFIDENCE},
             "evidence_ids": {"type": "array", "items": {"type": "string"}},
             "entity_ids": {"type": "array", "items": {"type": "string"}},
             "gaps": {"type": "string", "description": "What is unknown and what evidence would change this assessment."}},
             "required": ["statement", "category", "confidence", "evidence_ids", "entity_ids", "gaps"]}},
         "collection_gaps": {"type": "string", "description": "What the investigation could not determine from available sources."}},
         ["summary", "findings"])},
]


def grounded(name: str, haystack: str) -> bool:
    n = _norm(name)
    return bool(n) and n in _norm(haystack)


def _snippet(text: str, n: int = 280) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n] + "…"


class Toolkit:
    def __init__(self, store: Store, source, screener: Screener):
        self.store, self.source, self.screener = store, source, screener
        self.step = 0
        self.max_steps = 0
        self.finished: dict | None = None

    # ------------------------------------------------------------ helpers
    def _summarize_records(self, recs: list[dict]) -> dict:
        new_ev = new_ent = 0
        items = []
        for r in recs:
            res = self.store.ingest(r)
            new_ev += res["new_evidence"]
            new_ent += res["new_entities"]
            item: dict[str, Any] = {"evidence_id": r["id"], "kind": r["kind"], "title": r["title"],
                                    "year": r.get("year"), "snippet": _snippet(r.get("text", ""))}
            if r["kind"] == "work":
                orgs: dict[str, dict] = {}
                people = []
                for a in r.get("authors", [])[:12]:
                    people.append({"id": a["id"], "name": a["name"], "org_ids": [i["id"] for i in a.get("institutions", [])]})
                    for i in a.get("institutions", []):
                        orgs[i["id"]] = {"id": i["id"], "name": i["name"], "country": i.get("country")}
                item["organizations"] = list(orgs.values())
                item["people"] = people
            else:
                item["assignees"] = r.get("assignees", [])
                item["inventors"] = r.get("inventors", [])
            items.append(item)
        return {"returned": len(recs), "new_evidence": new_ev, "new_entities": new_ent, "results": items}

    # ------------------------------------------------------------ dispatch
    def call(self, name: str, args: dict) -> tuple[str, str]:
        """Execute a tool. Returns (result_json_for_model, one-line summary for the log)."""
        fn = getattr(self, f"t_{name}", None)
        if fn is None:
            out, summ = {"error": f"unknown tool {name}"}, "unknown tool"
        else:
            try:
                out, summ = fn(**args)
            except TypeError as e:
                out, summ = {"error": f"bad arguments: {e}"}, "bad arguments"
            except Exception as e:  # source/network errors go back to the agent
                out, summ = {"error": f"{type(e).__name__}: {e}"}, f"error: {type(e).__name__}"
        if isinstance(out, dict) and name != "submit_findings":
            out["steps_remaining"] = max(self.max_steps - self.step, 0)
        return json.dumps(out, default=str)[:24000], summ

    # ------------------------------------------------------------ tools
    def t_search_publications(self, query: str, limit: int = 10):
        recs = self.source.search_works(query, min(int(limit), 25))
        out = self._summarize_records(recs)
        return out, f"{out['returned']} publications ({out['new_evidence']} new)"

    def t_search_patents(self, query: str, limit: int = 10):
        if not getattr(self.source, "patents_enabled", False):
            return {"error": "patent source not configured"}, "patents unavailable"
        recs = self.source.search_patents(query, min(int(limit), 25))
        out = self._summarize_records(recs)
        return out, f"{out['returned']} patents ({out['new_evidence']} new)"

    def t_expand_entity(self, entity_id: str, limit: int = 15):
        ent = self.store.get_entity(entity_id)
        if not ent:
            return {"error": f"no entity {entity_id}"}, "unknown entity"
        recs = self.source.works_for_entity(entity_id, ent["name"], min(int(limit), 25))
        out = self._summarize_records(recs)
        return out, f"expanded {ent['name']}: {out['returned']} records ({out['new_evidence']} new)"

    def t_get_entity(self, entity_id: str):
        ent = self.store.get_entity(entity_id)
        if not ent:
            return {"error": f"no entity {entity_id}"}, "unknown entity"
        grouped: dict[tuple, dict] = {}
        for r in self.store.relationships_for(entity_id, limit=200):
            other = r["dst"] if r["src"] == entity_id else r["src"]
            key = (other, r["rel_type"])
            g = grouped.setdefault(key, {"other_id": other, "rel_type": r["rel_type"],
                                         "direction": "out" if r["src"] == entity_id else "in", "evidence_ids": []})
            g["evidence_ids"].append(r["evidence_id"])
        rels = []
        for g in list(grouped.values())[:40]:
            o = self.store.get_entity(g["other_id"]) or {}
            rels.append({**g, "other_name": o.get("name"), "other_country": o.get("country")})
        return {"entity": ent, "relationships": rels}, f"{ent['name']}: {len(grouped)} relationship groups"

    def t_find_entities(self, name: str):
        hits = [{"id": e["id"], "name": e["name"], "kind": e["kind"], "country": e["country"]}
                for e in self.store.find_entities(name)]
        return {"matches": hits}, f"{len(hits)} matches for '{name}'"

    def t_read_evidence(self, evidence_id: str):
        ev = self.store.get_evidence(evidence_id)
        if not ev:
            return {"error": f"no evidence {evidence_id}; only retrieved records can be read"}, "unknown evidence"
        raw = json.loads(ev["raw"])
        raw["text"] = (raw.get("text") or "")[:6000]
        return raw, f"read {evidence_id}"

    def t_screen_entity(self, entity_id: str):
        ent = self.store.get_entity(entity_id)
        if not ent:
            return {"error": f"no entity {entity_id}"}, "unknown entity"
        if not self.screener.loaded:
            return {"error": "no screening list loaded (see README: data/consolidated_screening_list.csv)"}, "no list"
        matches = self.screener.screen(ent["name"])
        self.store.set_entity_attr(entity_id, "screening", matches)
        best = matches[0]["match"] if matches else "none"
        return {"entity": ent["name"], "matches": matches,
                "note": "weak = different name similar enough to review; it does not establish a listing."}, \
            f"screened {ent['name']}: {best}"

    def t_register_entity(self, name: str, kind: str, evidence_id: str, country: str | None = None):
        hay = self.store.evidence_haystack(evidence_id)
        if not hay:
            return {"error": f"no evidence {evidence_id}"}, "rejected: unknown evidence"
        if not grounded(name, hay):
            return {"error": f"'{name}' does not appear in {evidence_id}; not registered"}, "rejected: ungrounded name"
        eid = f"agent:{slug(name)}"
        created = self.store.upsert_entity(eid, kind, name, country, {"first_evidence": evidence_id}, origin="agent")
        self.store.db.commit()
        return {"entity_id": eid, "created": bool(created)}, f"registered {name}"

    def t_add_relationship(self, src_id: str, dst_id: str, rel_type: str, evidence_id: str, rationale: str):
        if rel_type not in REL_TYPES:
            return {"error": f"rel_type must be one of {REL_TYPES}"}, "rejected: rel_type"
        s, d = self.store.get_entity(src_id), self.store.get_entity(dst_id)
        if not s or not d:
            return {"error": "both entities must exist in the graph"}, "rejected: unknown entity"
        hay = self.store.evidence_haystack(evidence_id)
        if not hay:
            return {"error": f"no evidence {evidence_id}"}, "rejected: unknown evidence"
        missing = [e["name"] for e in (s, d) if not grounded(e["name"], hay)]
        if missing:
            return {"error": f"{missing} not named in {evidence_id}; relationship not recorded"}, "rejected: ungrounded"
        self.store.add_relationship(src_id, dst_id, rel_type, evidence_id, origin="agent", rationale=rationale)
        self.store.db.commit()
        return {"recorded": True}, f"{s['name']} -{rel_type}-> {d['name']}"

    def t_record_lead(self, title: str, rationale: str, entity_ids: list[str] | None = None):
        lid = self.store.add_lead(title, rationale, entity_ids or [], self.step)
        return {"lead_id": lid}, f"lead #{lid}: {title}"

    def t_close_lead(self, lead_id: int, outcome: str):
        ok = self.store.close_lead(int(lead_id), outcome)
        return ({"closed": True} if ok else {"error": "no such lead"}), f"closed lead #{lead_id}"

    def t_get_status(self):
        ents = self.store.all_entities()
        rels = self.store.all_relationships()
        deg: dict[str, int] = {}
        for r in rels:
            deg[r["src"]] = deg.get(r["src"], 0) + 1
            deg[r["dst"]] = deg.get(r["dst"], 0) + 1
        orgs = [e for e in ents if e["kind"] == "organization"]
        top = sorted(orgs, key=lambda e: -deg.get(e["id"], 0))[:12]
        foreign = [{"id": e["id"], "name": e["name"], "country": e["country"],
                    "screened": "screening" in e["attrs"]} for e in orgs if e["country"] and e["country"] != "US"]
        return {"stats": self.store.stats(),
                "open_leads": [{"id": l["id"], "title": l["title"]} for l in self.store.leads() if l["status"] == "open"],
                "most_connected_orgs": [{"id": e["id"], "name": e["name"], "country": e["country"], "degree": deg.get(e["id"], 0)} for e in top],
                "foreign_orgs": foreign[:40]}, "status"

    def t_submit_findings(self, summary: str, findings: list[dict], collection_gaps: str = ""):
        self.finished = {"summary": summary, "findings": findings, "collection_gaps": collection_gaps}
        return {"received": len(findings)}, f"submitted {len(findings)} findings"
