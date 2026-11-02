import json

import pytest

from argus.agent import Investigator
from argus.baseline import run_baseline
from argus.evaluate import score
from argus.replay import ScriptedClient, _tu
from argus.report import render
from argus.screening import Screener
from argus.skeptic import check_finding
from argus.sources import get_source
from argus.sources.openalex import normalize_work
from argus.store import Store
from argus.tools import Toolkit


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "t.db")


@pytest.fixture
def tk(store):
    t = Toolkit(store, get_source("synthetic"), Screener.for_mode("synthetic"))
    t.max_steps = 50
    t.call("search_publications", {"query": "dilution refrigerator superconducting", "limit": 20})
    return t


def test_ingest_creates_provenance_linked_edges(tk, store):
    for r in store.all_relationships():
        assert store.get_evidence(r["evidence_id"]) is not None
    assert store.get_entity("syn:I03")["name"] == "Meridian Quantum Inc."


def test_register_entity_requires_name_in_evidence(tk, store):
    ok = json.loads(tk.call("register_entity", {"name": "Halvorsen Cryogenics", "kind": "organization", "evidence_id": "W-S03"})[0])
    assert ok["entity_id"] == "agent:halvorsen-cryogenics"
    bad = json.loads(tk.call("register_entity", {"name": "Acme Fridges", "kind": "organization", "evidence_id": "W-S03"})[0])
    assert "error" in bad


def test_add_relationship_rejects_ungrounded(tk, store):
    tk.call("register_entity", {"name": "Halvorsen Cryogenics", "kind": "organization", "evidence_id": "W-S03"})
    # Pell Valley is not named in W-S03
    out = json.loads(tk.call("add_relationship", {"src_id": "syn:I01", "dst_id": "agent:halvorsen-cryogenics",
                                                  "rel_type": "DEPENDS_ON", "evidence_id": "W-S03", "rationale": "x"})[0])
    assert "error" in out
    out = json.loads(tk.call("add_relationship", {"src_id": "syn:I04", "dst_id": "agent:halvorsen-cryogenics",
                                                  "rel_type": "DEPENDS_ON", "evidence_id": "W-S03", "rationale": "only vendor"})[0])
    assert out["recorded"]


def test_screening_distinguishes_near_names():
    s = Screener.for_mode("synthetic")
    assert s.screen("Eastern Institute of Quantum Engineering")[0]["match"] == "exact"
    assert s.screen("Eastern Institute of Quantum Sciences")[0]["match"] == "weak"
    assert s.screen("Northgate University") == []


def test_skeptic_rejects_fabricated_evidence(tk, store):
    f = check_finding({"statement": "x", "category": "dependency", "confidence": "low",
                       "evidence_ids": ["W-FAKE"], "entity_ids": ["syn:I03"]}, store)
    assert f["verdict"] == "rejected"


def test_skeptic_rejects_listing_claim_on_weak_match(store):
    t = Toolkit(store, get_source("synthetic"), Screener.for_mode("synthetic"))
    t.max_steps = 50
    t.call("search_publications", {"query": "photonic lattices topological", "limit": 5})
    t.call("screen_entity", {"entity_id": "syn:I08"})
    f = check_finding({"statement": "Eastern Institute of Quantum Sciences is on the entity list.", "category": "foreign_link",
                       "confidence": "moderate", "evidence_ids": ["W-S10"], "entity_ids": ["syn:I08"]}, store)
    assert f["verdict"] == "rejected"


def test_skeptic_downgrades_unresolved_identity(store):
    t = Toolkit(store, get_source("synthetic"), Screener.for_mode("synthetic"))
    t.max_steps = 50
    t.call("search_publications", {"query": "fluxonium", "limit": 3})
    t.call("search_patents", {"query": "Josephson parametric amplifier transformer", "limit": 3})
    f = check_finding({"statement": "Wei Tan works for both Pell Valley and Shenhai.", "category": "foreign_link",
                       "confidence": "high", "evidence_ids": ["W-S01", "P-S01"],
                       "entity_ids": ["syn:A09", "syn:inv-wei-tan-P-S01"]}, store)
    assert f["verdict"] == "downgraded" and f["confidence"] == "low"


def test_skeptic_high_confidence_needs_two_sources(tk, store):
    f = check_finding({"statement": "Meridian uses a Halvorsen system.", "category": "dependency", "confidence": "high",
                       "evidence_ids": ["W-S04"], "entity_ids": ["syn:I03"]}, store)
    assert f["confidence"] == "moderate" and f["verdict"] == "downgraded"


def test_full_loop_with_scripted_client(store):
    events = []
    res = Investigator(store, get_source("synthetic"), Screener.for_mode("synthetic"), ScriptedClient(),
                       "scripted", 40, on_event=events.append).run()
    assert any(e["type"] == "done" for e in events)
    sc = score(store)
    assert sc["facts_found"] == "5/5"
    assert sc["false_flags"] == 0 and sc["overclaims"] == 0
    md = render(store)
    assert "Key judgments" in md and "Halvorsen" in md
    assert all(d["reasoning"] for d in store.decisions())


def test_budget_forces_submission(store):
    # A client that never stops searching must still end with a submission once the budget is hit.
    from argus.replay import _Resp

    class Looping:
        def __init__(self):
            self.messages = self

        def create(self, **kw):
            if kw.get("tool_choice", {}).get("name") == "submit_findings":
                return _Resp([_tu("submit_findings", "budget", summary="s", findings=[])], "tool_use")
            return _Resp([_tu("search_publications", "keep going", query="qubit")], "tool_use")

    res = Investigator(store, get_source("synthetic"), Screener.for_mode("synthetic"), Looping(), "x", 5).run()
    assert res["summary"] == "s"
    assert store.get_meta("steps_used") <= 6


def test_baseline_runs_and_is_scored(store):
    run_baseline(store, get_source("synthetic"), Screener.for_mode("synthetic"))
    sc = score(store)
    assert sc["findings_submitted"] > 0


def test_openalex_normalization():
    w = {"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1/x", "title": "T", "publication_year": 2024,
         "abstract_inverted_index": {"hello": [0], "world": [1]},
         "authorships": [{"author": {"id": "https://openalex.org/A9", "display_name": "Ada"},
                          "institutions": [{"id": "https://openalex.org/I5", "display_name": "Uni", "country_code": "US", "type": "education"}]}]}
    n = normalize_work(w)
    assert n["id"] == "oa:W1" and n["text"] == "hello world"
    assert n["authors"][0]["institutions"][0]["id"] == "oa:I5"


def test_tool_errors_return_to_agent(store):
    class Broken:
        patents_enabled = False
        def search_works(self, *a, **k):
            raise ConnectionError("network down")
    t = Toolkit(store, Broken(), Screener.for_mode("synthetic"))
    out = json.loads(t.call("search_publications", {"query": "x"})[0])
    assert "network down" in out["error"]
    out = json.loads(t.call("search_patents", {"query": "x"})[0])
    assert "not configured" in out["error"]
