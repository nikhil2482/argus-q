"""Persistent investigation memory: evidence, entities, relationships, leads,
decisions and findings, all in one SQLite file per run.

Design rule: every relationship must point at an evidence record that was
actually retrieved from a source. Nothing enters the graph without provenance.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY, source TEXT, kind TEXT, url TEXT, title TEXT,
    text TEXT, year INTEGER, raw TEXT, fetched_at REAL
);
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY, kind TEXT, name TEXT, country TEXT, attrs TEXT,
    origin TEXT DEFAULT 'ingest'
);
CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    src TEXT, dst TEXT, rel_type TEXT, evidence_id TEXT,
    origin TEXT, rationale TEXT,
    UNIQUE(src, dst, rel_type, evidence_id)
);
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, rationale TEXT,
    entity_ids TEXT, status TEXT DEFAULT 'open', outcome TEXT, step INTEGER
);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, step INTEGER, action TEXT,
    args TEXT, reasoning TEXT, result_summary TEXT, ts REAL
);
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, statement TEXT, category TEXT,
    confidence TEXT, evidence_ids TEXT, entity_ids TEXT, gaps TEXT,
    verdict TEXT, verdict_notes TEXT
);
CREATE INDEX IF NOT EXISTS rel_src ON relationships(src);
CREATE INDEX IF NOT EXISTS rel_dst ON relationships(dst);
"""


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    # ---------------- meta ----------------
    def set_meta(self, key: str, value: Any) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, json.dumps(value)))
        self.db.commit()

    def get_meta(self, key: str, default: Any = None) -> Any:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    # ---------------- evidence ----------------
    def add_evidence(self, rec: dict) -> bool:
        """Insert a normalized source record. Returns True if it was new."""
        cur = self.db.execute(
            "INSERT OR IGNORE INTO evidence VALUES (?,?,?,?,?,?,?,?,?)",
            (rec["id"], rec["source"], rec["kind"], rec.get("url"), rec.get("title"),
             rec.get("text") or "", rec.get("year"), json.dumps(rec), time.time()),
        )
        return cur.rowcount > 0

    def get_evidence(self, evidence_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM evidence WHERE id=?", (evidence_id,)).fetchone()
        return dict(row) if row else None

    def evidence_haystack(self, evidence_id: str) -> str:
        """All text an evidence record can vouch for: title, abstract, and the
        names of every entity the record itself lists (authors, affiliations,
        assignees, inventors)."""
        ev = self.get_evidence(evidence_id)
        if not ev:
            return ""
        raw = json.loads(ev["raw"])
        names: list[str] = []
        for a in raw.get("authors", []):
            names.append(a.get("name", ""))
            names += [i.get("name", "") for i in a.get("institutions", [])]
        names += [x.get("name", "") for x in raw.get("assignees", []) + raw.get("inventors", [])]
        return " ".join([ev["title"] or "", ev["text"] or "", *names]).lower()

    def all_evidence(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT id, source, kind, url, title, year FROM evidence ORDER BY id")]

    # ---------------- entities ----------------
    def upsert_entity(self, eid: str, kind: str, name: str, country: str | None = None,
                      attrs: dict | None = None, origin: str = "ingest") -> bool:
        existing = self.get_entity(eid)
        if existing:
            merged = {**existing["attrs"], **(attrs or {})}
            self.db.execute("UPDATE entities SET attrs=?, country=COALESCE(country, ?) WHERE id=?",
                            (json.dumps(merged), country, eid))
            return False
        self.db.execute("INSERT INTO entities VALUES (?,?,?,?,?,?)",
                        (eid, kind, name, country, json.dumps(attrs or {}), origin))
        return True

    def get_entity(self, eid: str) -> dict | None:
        row = self.db.execute("SELECT * FROM entities WHERE id=?", (eid,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["attrs"] = json.loads(d["attrs"] or "{}")
        return d

    def set_entity_attr(self, eid: str, key: str, value: Any) -> None:
        ent = self.get_entity(eid)
        if ent:
            ent["attrs"][key] = value
            self.db.execute("UPDATE entities SET attrs=? WHERE id=?", (json.dumps(ent["attrs"]), eid))
            self.db.commit()

    def find_entities(self, query: str, limit: int = 15) -> list[dict]:
        terms = [t for t in re.split(r"\W+", query.lower()) if t]
        rows = self.db.execute("SELECT * FROM entities").fetchall()
        scored = []
        for r in rows:
            name = (r["name"] or "").lower()
            score = sum(1 for t in terms if t in name)
            if score:
                scored.append((score, dict(r)))
        scored.sort(key=lambda x: (-x[0], x[1]["name"]))
        return [s[1] for s in scored[:limit]]

    def org_id_by_name(self, name: str) -> str | None:
        from .screening import _norm
        key = _norm(name)
        for r in self.db.execute("SELECT id, name FROM entities WHERE kind='organization'"):
            if _norm(r["name"]) == key:
                return r["id"]
        return None

    def all_entities(self) -> list[dict]:
        out = []
        for r in self.db.execute("SELECT * FROM entities ORDER BY name"):
            d = dict(r)
            d["attrs"] = json.loads(d["attrs"] or "{}")
            out.append(d)
        return out

    # ---------------- relationships ----------------
    def add_relationship(self, src: str, dst: str, rel_type: str, evidence_id: str,
                         origin: str = "ingest", rationale: str = "") -> bool:
        if not self.get_evidence(evidence_id):
            raise ValueError(f"evidence {evidence_id} does not exist")
        cur = self.db.execute(
            "INSERT OR IGNORE INTO relationships (src,dst,rel_type,evidence_id,origin,rationale) VALUES (?,?,?,?,?,?)",
            (src, dst, rel_type, evidence_id, origin, rationale))
        return cur.rowcount > 0

    def relationships_for(self, eid: str, limit: int = 40) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM relationships WHERE src=? OR dst=? ORDER BY id LIMIT ?", (eid, eid, limit))
        return [dict(r) for r in rows]

    def all_relationships(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM relationships ORDER BY id")]

    def entities_for_evidence(self, evidence_id: str) -> list[str]:
        rows = self.db.execute(
            "SELECT DISTINCT src, dst FROM relationships WHERE evidence_id=?", (evidence_id,)).fetchall()
        ids: set[str] = set()
        for r in rows:
            ids.update([r["src"], r["dst"]])
        return sorted(ids)

    # ---------------- ingestion ----------------
    def ingest(self, rec: dict) -> dict:
        """Store a normalized record and the structured relationships it states
        outright (author affiliations, co-publication, patent assignment)."""
        new_ev = self.add_evidence(rec)
        new_ents = 0
        if rec["kind"] == "work":
            inst_ids: list[str] = []
            for a in rec.get("authors", []):
                if not a.get("id"):
                    continue
                new_ents += self.upsert_entity(a["id"], "person", a["name"])
                for inst in a.get("institutions", []):
                    if not inst.get("id"):
                        continue
                    new_ents += self.upsert_entity(inst["id"], "organization", inst["name"],
                                                   inst.get("country"), {"org_type": inst.get("type")})
                    self.add_relationship(a["id"], inst["id"], "AFFILIATED_WITH", rec["id"])
                    if inst["id"] not in inst_ids:
                        inst_ids.append(inst["id"])
            for i, x in enumerate(inst_ids):
                for y in inst_ids[i + 1:]:
                    s, d = sorted([x, y])
                    self.add_relationship(s, d, "CO_PUBLISHED_WITH", rec["id"])
        elif rec["kind"] == "patent":
            for asg in rec.get("assignees", []):
                # Light entity resolution for organizations only: a patent assignee whose
                # normalized name exactly equals a known organization is treated as that organization.
                # People are never merged on name alone.
                org_id = self.org_id_by_name(asg["name"]) or asg["id"]
                new_ents += self.upsert_entity(org_id, "organization", asg["name"],
                                               asg.get("country"), {"org_type": "company"})
                for inv in rec.get("inventors", []):
                    new_ents += self.upsert_entity(inv["id"], "person", inv["name"])
                    self.add_relationship(inv["id"], org_id, "INVENTOR_FOR", rec["id"])
        self.db.commit()
        return {"new_evidence": bool(new_ev), "new_entities": int(new_ents)}

    # ---------------- leads / decisions / findings ----------------
    def add_lead(self, title: str, rationale: str, entity_ids: list[str], step: int) -> int:
        cur = self.db.execute("INSERT INTO leads (title, rationale, entity_ids, step) VALUES (?,?,?,?)",
                              (title, rationale, json.dumps(entity_ids), step))
        self.db.commit()
        return cur.lastrowid

    def close_lead(self, lead_id: int, outcome: str) -> bool:
        cur = self.db.execute("UPDATE leads SET status='closed', outcome=? WHERE id=?", (outcome, lead_id))
        self.db.commit()
        return cur.rowcount > 0

    def leads(self) -> list[dict]:
        out = []
        for r in self.db.execute("SELECT * FROM leads ORDER BY id"):
            d = dict(r)
            d["entity_ids"] = json.loads(d["entity_ids"] or "[]")
            out.append(d)
        return out

    def log_decision(self, step: int, action: str, args: dict, reasoning: str, result_summary: str) -> None:
        self.db.execute("INSERT INTO decisions (step, action, args, reasoning, result_summary, ts) VALUES (?,?,?,?,?,?)",
                        (step, action, json.dumps(args), reasoning, result_summary, time.time()))
        self.db.commit()

    def decisions(self) -> list[dict]:
        out = []
        for r in self.db.execute("SELECT * FROM decisions ORDER BY id"):
            d = dict(r)
            d["args"] = json.loads(d["args"] or "{}")
            out.append(d)
        return out

    def save_findings(self, findings: Iterable[dict]) -> None:
        self.db.execute("DELETE FROM findings")
        for f in findings:
            self.db.execute(
                "INSERT INTO findings (statement, category, confidence, evidence_ids, entity_ids, gaps, verdict, verdict_notes) VALUES (?,?,?,?,?,?,?,?)",
                (f["statement"], f.get("category", "context"), f.get("confidence", "low"),
                 json.dumps(f.get("evidence_ids", [])), json.dumps(f.get("entity_ids", [])),
                 f.get("gaps", ""), f.get("verdict", "unchecked"), f.get("verdict_notes", "")))
        self.db.commit()

    def findings(self) -> list[dict]:
        out = []
        for r in self.db.execute("SELECT * FROM findings ORDER BY id"):
            d = dict(r)
            d["evidence_ids"] = json.loads(d["evidence_ids"] or "[]")
            d["entity_ids"] = json.loads(d["entity_ids"] or "[]")
            out.append(d)
        return out

    def stats(self) -> dict:
        q = lambda t: self.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        return {"evidence": q("evidence"), "entities": q("entities"),
                "relationships": q("relationships"), "leads": q("leads"),
                "decisions": q("decisions"), "findings": q("findings")}
