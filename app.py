"""ARGUS-Q dashboard.  Run with:  streamlit run app.py"""
from __future__ import annotations

import html
import json
import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from argus.agent import DEFAULT_MISSION, DEFAULT_MODEL, Investigator
from argus.graph import to_html
from argus.report import render
from argus.screening import Screener
from argus.sources import get_source
from argus.store import Store

RUNS = Path("runs")
RUNS.mkdir(exist_ok=True)

st.set_page_config(page_title="ARGUS-Q", page_icon="🛰️", layout="wide")
st.markdown("""
<style>
  .block-container {padding-top: 1.6rem; max-width: 1400px;}
  .argus-head {display:flex; align-items:baseline; gap:.8rem; margin-bottom:.2rem;}
  .argus-head h1 {font-size:1.9rem; margin:0; letter-spacing:.08em;}
  .argus-sub {color:#94a3b8; font-size:.95rem;}
  .why {color:#94a3b8; font-size:.9rem; margin:.1rem 0 .6rem 0;}
  .legend span {display:inline-block; margin-right:1rem; font-size:.85rem;}
  .dot {display:inline-block; width:.7rem; height:.7rem; border-radius:50%; margin-right:.3rem; vertical-align:middle;}
</style>""", unsafe_allow_html=True)

st.markdown('<div class="argus-head"><h1>ARGUS-Q</h1><span class="argus-sub">Autonomous strategic-technology intelligence · public data only</span></div>',
            unsafe_allow_html=True)


def run_files() -> list[Path]:
    return sorted(RUNS.glob("*.db"), reverse=True)


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.subheader("New investigation")
    mode_label = st.radio("Data", ["Live public data", "Synthetic test world"], index=0,
                          help="Synthetic = fictional ecosystem with a known answer key, used for evaluation.")
    mode = "live" if mode_label.startswith("Live") else "synthetic"
    mission = st.text_area("Mission", DEFAULT_MISSION, height=150)
    steps = st.slider("Step budget", 10, 60, 30)
    model = st.text_input("Model", DEFAULT_MODEL)
    llm_skeptic = st.toggle("LLM reviewer (second-opinion check)", value=True)
    has_key = bool(os.getenv("ANTHROPIC_API_KEY"))
    go = st.button("Run investigation", type="primary", disabled=not has_key, width="stretch")
    if not has_key:
        st.caption("Set ANTHROPIC_API_KEY in .env to run the agent.")
    demo = st.button("Scripted replay (no key)", width="stretch")
    st.divider()
    st.subheader("Past runs")
    files = run_files()
    pick = st.selectbox("Open", files, format_func=lambda p: p.stem, index=0 if files else None)
    if pick is not None and st.button("Load run", width="stretch"):
        st.session_state["db"] = str(pick)


def execute(client, mode: str, model: str, kind: str, note: str | None = None):
    import time
    store = Store(RUNS / f"{time.strftime('%Y%m%d-%H%M%S')}-{mode}-{kind}.db")
    store.set_meta("mode", mode)
    if note:
        store.set_meta("note", note)
    with st.status("Investigating…", expanded=True) as status:
        def on_event(e):
            if e["type"] == "action":
                st.markdown(f"**{e['step']}. {e['tool']}** — {e['summary']}")
                if e["reasoning"]:
                    st.markdown(f'<div class="why">{html.escape(e["reasoning"])}</div>', unsafe_allow_html=True)
            elif e["type"] == "review":
                status.update(label=f"Reviewing {e['count']} findings…")
        Investigator(store, get_source(mode), Screener.for_mode(mode), client, model, steps if kind == "agent" else 40,
                     llm_skeptic=llm_skeptic, on_event=on_event).run(mission if kind == "agent" else DEFAULT_MISSION)
        if kind == "replay":
            store.set_meta("kind", "replay")
        Path(store.path).with_suffix(".md").write_text(render(store))
        status.update(label="Investigation complete", state="complete", expanded=False)
    st.session_state["db"] = store.path


if go:
    import anthropic
    execute(anthropic.Anthropic(), mode, model, "agent")
if demo:
    from argus.replay import ScriptedClient
    execute(ScriptedClient(), "synthetic", "scripted-replay", "replay",
            note="Scripted replay against the fictional test world; not a live agent run.")

db = st.session_state.get("db") or (str(files[0]) if files else None)
if not db:
    st.info("Run an investigation, or click **Scripted replay** to see the interface with the fictional test world.")
    st.stop()

store = Store(db)
s = store.stats()
findings = store.findings()
kept = [f for f in findings if f["verdict"] != "rejected"]
if store.get_meta("note"):
    st.warning(store.get_meta("note"))
st.markdown(f"**Mission:** {store.get_meta('mission', '')}")
c = st.columns(6)
c[0].metric("Evidence", s["evidence"])
c[1].metric("Entities", s["entities"])
c[2].metric("Relationships", s["relationships"])
c[3].metric("Agent steps", store.get_meta("steps_used", "—"))
c[4].metric("Findings kept", len(kept))
c[5].metric("Rejected in review", len(findings) - len(kept))

tabs = st.tabs(["Assessment", "Network", "Agent reasoning", "Entity inspector", "Evidence", "Evaluation"])

with tabs[0]:
    st.markdown(render(store).split("\n", 1)[1])
    st.download_button("Download assessment (.md)", render(store), file_name=f"{Path(db).stem}.md")

with tabs[1]:
    st.markdown('<div class="legend">'
                '<span><i class="dot" style="background:#3b82f6"></i>U.S. organization</span>'
                '<span><i class="dot" style="background:#94a3b8"></i>Foreign organization</span>'
                '<span><i class="dot" style="background:#ef4444"></i>Exact/strong screening match</span>'
                '<span><i class="dot" style="background:#f59e0b"></i>Weak match (review)</span>'
                '<span><i class="dot" style="background:#10b981"></i>Agent-extracted entity / edge</span>'
                '<span>▲ person</span></div>', unsafe_allow_html=True)
    graph_html = to_html(store)
    if hasattr(st, "iframe"):
        st.iframe(graph_html, height=660)
    else:  # older Streamlit
        components.html(graph_html, height=660, scrolling=False)

with tabs[2]:
    st.caption("Every action the agent took, in order, with the reasoning it gave at the time.")
    for d in store.decisions():
        with st.expander(f"{d['step']}. {d['action']} — {d['result_summary']}"):
            st.markdown(f"**Why:** {d['reasoning'] or '—'}")
            st.json(d["args"])
    leads = store.leads()
    if leads:
        st.subheader("Leads")
        st.dataframe([{"#": l["id"], "status": l["status"], "lead": l["title"], "outcome": l["outcome"] or ""} for l in leads],
                     width="stretch", hide_index=True)

with tabs[3]:
    ents = store.all_entities()
    orgs_first = sorted(ents, key=lambda e: (e["kind"] != "organization", e["name"] or ""))
    sel = st.selectbox("Entity", orgs_first, format_func=lambda e: f"{e['name']}  ({e['kind']}, {e['country'] or '—'})")
    if sel:
        st.markdown(f"**ID:** `{sel['id']}` · **origin:** {sel['origin']}")
        if sel["attrs"].get("screening") is not None:
            st.markdown("**Screening:**")
            st.json(sel["attrs"]["screening"] or "no matches")
        rows = []
        for r in store.relationships_for(sel["id"], 300):
            other = store.get_entity(r["dst"] if r["src"] == sel["id"] else r["src"]) or {}
            ev = store.get_evidence(r["evidence_id"]) or {}
            rows.append({"relationship": r["rel_type"], "with": other.get("name"), "country": other.get("country"),
                         "evidence": r["evidence_id"], "source title": ev.get("title"), "link": ev.get("url"),
                         "added by": r["origin"], "rationale": r["rationale"] or ""})
        st.dataframe(rows, width="stretch", hide_index=True,
                     column_config={"link": st.column_config.LinkColumn("link")})

with tabs[4]:
    st.dataframe(store.all_evidence(), width="stretch", hide_index=True,
                 column_config={"url": st.column_config.LinkColumn("url")})
    eid = st.text_input("Read evidence by id")
    if eid and store.get_evidence(eid):
        st.json(json.loads(store.get_evidence(eid)["raw"]))

with tabs[5]:
    if store.get_meta("mode") != "synthetic":
        st.info("Evaluation scores are available for runs on the synthetic test world, which has a known answer key.")
    else:
        from argus.evaluate import score
        sc = score(store)
        m = st.columns(4)
        m[0].metric("Answer-key facts found", sc["facts_found"])
        m[1].metric("False flags", sc["false_flags"])
        m[2].metric("Overclaims", sc["overclaims"])
        m[3].metric("Rejected by reviewer", sc["findings_rejected_by_skeptic"])
        for f in sc["facts"]:
            st.markdown(f"{'✅' if f['found'] else '❌'} **{f['id']}** {f['label']}")
        if sc["false_flag_examples"]:
            st.markdown("**False-flag examples:** " + "; ".join(sc["false_flag_examples"]))
        res = RUNS / "eval_results.json"
        if res.exists():
            st.subheader("Agent vs. baseline (python run.py eval)")
            st.dataframe([{k: v for k, v in r.items() if k not in ("facts", "false_flag_examples", "overclaim_examples")}
                          for r in json.loads(res.read_text())], width="stretch", hide_index=True)
