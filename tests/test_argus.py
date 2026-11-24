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
            last = kw["messages"][-1]["content"]
            if isinstance(last, list) and any("budget exhausted" in (b.get("text") or "") for b in last):
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


def test_cache_breakpoints_and_usage(store):
    """Every request caches the system prompt and moves a single breakpoint to the
    newest message, staying under the API's limit of four breakpoints."""
    from types import SimpleNamespace

    seen = []

    class Recording(ScriptedClient):
        def create(self, **kw):
            if "system" in kw:  # agent steps (reviewer calls have no system prompt)
                msgs = kw["messages"]
                marks = sum(1 for m in msgs if isinstance(m["content"], list)
                            for b in m["content"] if "cache_control" in b)
                seen.append((kw["system"][0].get("cache_control"), marks,
                             "cache_control" in msgs[-1]["content"][-1]))
            r = super().create(**kw)
            r.usage = SimpleNamespace(input_tokens=100, output_tokens=10,
                                      cache_creation_input_tokens=50, cache_read_input_tokens=900)
            return r

    res = Investigator(store, get_source("synthetic"), Screener.for_mode("synthetic"), Recording(),
                       "claude-sonnet-5-5", 40).run()
    assert seen and all(sys_cc == {"type": "ephemeral"} and marks == 1 and last for sys_cc, marks, last in seen)
    u = res["usage"]
    assert u["cache_read_tokens"] > 0 and u["approx_cost_usd"] > 0
    assert store.get_meta("usage")["api_calls"] == u["api_calls"]


def test_search_results_are_compact_and_valid_json(store):
    t = Toolkit(store, get_source("synthetic"), Screener.for_mode("synthetic"))
    t.max_steps = 50
    out = json.loads(t.call("search_publications", {"query": "superconducting qubit", "limit": 25})[0])
    for r in out["results"]:
        assert len(r["snippet"]) <= 221 and len(r["authors"]) <= 6


def test_negated_listing_statement_is_not_a_listing_claim(tk, store):
    from argus.skeptic import asserts_listing
    assert asserts_listing("Shenhai is on the entity list.")
    assert not asserts_listing("None of these collaborators are on the screening list.")
    assert not asserts_listing("It is a weak match to a listed institute.")
    f = check_finding({"statement": "Meridian's partners show no sign of concern; none are listed.",
                       "category": "context", "confidence": "low", "evidence_ids": ["W-S04"],
                       "entity_ids": ["syn:I03"]}, store)
    assert f["verdict"] != "rejected"


def test_submit_gets_one_revision_with_hints(tk, store):
    bad = {"statement": "Halvorsen supplies Meridian.", "category": "dependency", "confidence": "moderate",
           "evidence_ids": ["W-S04"], "entity_ids": ["syn:I03", "syn:I04"], "gaps": "x"}
    out = json.loads(tk.call("submit_findings", {"summary": "s", "findings": [bad]})[0])
    assert out["accepted"] is False and tk.finished is None
    hints = out["problems"][0]["evidence_that_names_these_entities"]
    assert "W-S03" in hints["Coldline Systems Inc."]
    # second submission is accepted as-is; the reviewer then judges it
    tk.call("submit_findings", {"summary": "s", "findings": [bad]})
    assert tk.finished is not None


def test_unknown_entity_suggests_real_ids(tk):
    out = json.loads(tk.call("screen_entity", {"entity_id": "syn:asg-meridian-quantum"})[0])
    assert any(h["id"] == "syn:I03" for h in out["did_you_mean"])


def test_register_entity_reuses_known_org(tk):
    out = json.loads(tk.call("register_entity", {"name": "Meridian Quantum", "kind": "organization",
                                                  "evidence_id": "W-S02"})[0])
    assert out["entity_id"] == "syn:I03" and out["created"] is False


def test_no_forced_tool_choice_anywhere(store):
    """Claude Sonnet 5.5 rejects forced tool_choice with a 400, so no request may send it."""
    sent = []

    class Spy(ScriptedClient):
        def create(self, **kw):
            sent.append(kw.get("tool_choice"))
            return super().create(**kw)

    Investigator(store, get_source("synthetic"), Screener.for_mode("synthetic"), Spy(), "claude-sonnet-5-5", 40).run()
    assert sent and all(tc in (None, {"type": "auto"}) for tc in sent)


def test_named_entities_are_attached(store):
    t = Toolkit(store, get_source("synthetic"), Screener.for_mode("synthetic"))
    t.max_steps = 50
    t.call("search_publications", {"query": "dilution refrigerator superconducting", "limit": 20})
    t.call("search_publications", {"query": "parametric amplifier readout", "limit": 10})
    f = check_finding({"statement": "Halvorsen systems are used across Pell Valley, Northgate and Meridian.",
                       "category": "dependency", "confidence": "moderate",
                       "evidence_ids": ["W-S01", "W-S04"], "entity_ids": ["syn:I03"]}, store)
    assert {"syn:I01", "syn:I02", "syn:I03"} <= set(f["entity_ids"])
    g = check_finding({"statement": "Northgate University's Lena Voss also lists the Eastern Institute of Quantum Engineering.",
                       "category": "foreign_link", "confidence": "low",
                       "evidence_ids": ["W-S12"], "entity_ids": ["syn:I02", "syn:I07"]}, store)
    assert "syn:A03" in g["entity_ids"]
    # an ambiguous short form ("Eastern Institute") attaches nothing by itself
    t.call("search_publications", {"query": "quantum key distribution metropolitan fiber", "limit": 3})
    assert store.get_evidence("W-S11")
    h = check_finding({"statement": "An Eastern Institute paper on fiber QKD.", "category": "context",
                       "confidence": "low", "evidence_ids": ["W-S11"], "entity_ids": []}, store)
    assert not {"syn:I07", "syn:I08"} & set(h["entity_ids"])


def test_real_list_format(tmp_path):
    """The real Consolidated Screening List: huge fields, people and vessels mixed in,
    country only inside the address."""
    import csv
    p = tmp_path / "csl.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["_id", "source", "type", "name", "addresses", "alt_names"])
        w.writerow(["1", "Entity List (EL)", "Entity", "Origin Quantum Computing Technology (Hefei) Co., Ltd.",
                    "Building D8, Hefei, CN; " + "x" * 300000, "Origin Quantum; Benyuan Quantum"])
        w.writerow(["2", "SDN", "Individual", "Zhang Wei", "Beijing, CN", ""])
        w.writerow(["3", "Entity List (EL)", "Entity", "Sichuan University", "Chengdu, CN", ""])
    s = Screener.for_mode("live", p)
    assert {e["matched_name"] for e in s.entries} == {"Origin Quantum Computing Technology (Hefei) Co., Ltd.",
                                                      "Origin Quantum", "Benyuan Quantum", "Sichuan University"}
    hit = s.screen("Origin Quantum")[0]
    assert hit["match"] == "exact" and hit["country"] == "CN"
    assert s.screen("Tsinghua University") == []
