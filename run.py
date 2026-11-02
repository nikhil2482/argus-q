#!/usr/bin/env python3
"""ARGUS-Q command line.

  python run.py investigate [--mode live|synthetic] [--mission "..."] [--steps 30]
  python run.py baseline    [--mode live|synthetic]
  python run.py eval        [--trials 3]          # agent vs baseline on the synthetic benchmark
  python run.py demo                              # scripted replay, no API key needed
  python run.py report runs/<file>.db             # re-render an assessment
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from argus.agent import DEFAULT_MISSION, DEFAULT_MODEL, Investigator
from argus.baseline import run_baseline
from argus.report import render
from argus.screening import Screener
from argus.sources import get_source
from argus.store import Store

RUNS = Path("runs")


def new_store(mode: str, kind: str) -> Store:
    RUNS.mkdir(exist_ok=True)
    s = Store(RUNS / f"{time.strftime('%Y%m%d-%H%M%S')}-{mode}-{kind}.db")
    s.set_meta("mode", mode)
    return s


def printer(e: dict) -> None:
    if e["type"] == "action":
        print(f"[{e['step']:>2}] {e['tool']:<20} {e['summary']}")
        if e["reasoning"]:
            print(f"      why: {e['reasoning'][:160]}")
    elif e["type"] == "review":
        print(f"\nReviewing {e['count']} findings…")


def write_report(store: Store) -> Path:
    path = Path(store.path).with_suffix(".md")
    path.write_text(render(store))
    return path


def make_client():
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Add it to .env (see .env.example), or run `python run.py demo`.")
    import anthropic
    return anthropic.Anthropic()


def cmd_investigate(a):
    store = new_store(a.mode, "agent")
    inv = Investigator(store, get_source(a.mode), Screener.for_mode(a.mode), make_client(), a.model,
                       a.steps, llm_skeptic=not a.no_llm_skeptic, on_event=printer)
    res = inv.run(a.mission)
    for f in res["findings"]:
        print(f"  [{f['verdict']:<10}] ({f['confidence']}) {f['statement'][:110]}")
    print(f"\nAssessment: {write_report(store)}\nRun database: {store.path}")
    if a.mode == "synthetic":
        from argus.evaluate import score
        print(json.dumps({k: v for k, v in score(store).items() if k != 'facts'}, indent=2))


def cmd_baseline(a):
    store = new_store(a.mode, "baseline")
    run_baseline(store, get_source(a.mode), Screener.for_mode(a.mode))
    print(f"Assessment: {write_report(store)}")
    if a.mode == "synthetic":
        from argus.evaluate import score
        print(json.dumps({k: v for k, v in score(store).items() if k != 'facts'}, indent=2))


def cmd_demo(a):
    from argus.replay import ScriptedClient
    store = new_store("synthetic", "replay")
    store.set_meta("note", "Scripted replay against the fictional test world; not a live agent run.")
    Investigator(store, get_source("synthetic"), Screener.for_mode("synthetic"), ScriptedClient(),
                 "scripted-replay", 40, on_event=printer).run(DEFAULT_MISSION)
    store.set_meta("kind", "replay")
    print(f"\nAssessment: {write_report(store)}\nOpen the dashboard with: streamlit run app.py")


def cmd_eval(a):
    from argus.evaluate import score
    client = make_client()
    rows = []
    for t in range(a.trials):
        store = new_store("synthetic", f"agent-eval{t + 1}")
        print(f"\n=== Agent trial {t + 1}/{a.trials} ===")
        Investigator(store, get_source("synthetic"), Screener.for_mode("synthetic"), client, a.model, a.steps,
                     on_event=printer).run(DEFAULT_MISSION)
        write_report(store)
        rows.append({"run": f"agent #{t + 1}", **score(store)})
    store = new_store("synthetic", "baseline-eval")
    run_baseline(store, get_source("synthetic"), Screener.for_mode("synthetic"))
    write_report(store)
    rows.append({"run": "baseline", **score(store)})

    cols = ["facts_found", "false_flags", "overclaims", "findings_kept", "findings_rejected_by_skeptic", "steps", "evidence_records"]
    md = ["| run | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
    md += ["| " + r["run"] + " | " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    table = "\n".join(md)
    print("\n" + table)
    out = RUNS / "eval_results.json"
    out.write_text(json.dumps(rows, indent=2))
    Path("docs").mkdir(exist_ok=True)
    detail = ["# Evaluation results", "", f"Model: `{a.model}` · step budget: {a.steps} · trials: {a.trials}", "", table, "",
              "## Facts found per run", ""]
    for r in rows:
        detail.append(f"**{r['run']}:** " + ", ".join(f"{f['id']} {'✓' if f['found'] else '✗'}" for f in r["facts"]))
    Path("docs/evaluation.md").write_text("\n".join(detail) + "\n")
    print(f"\nSaved {out} and docs/evaluation.md")


def cmd_report(a):
    store = Store(a.db)
    print(write_report(store))


def main():
    p = argparse.ArgumentParser(description="ARGUS-Q autonomous quantum intelligence agent")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("investigate")
    i.add_argument("--mode", default="live", choices=["live", "synthetic"])
    i.add_argument("--mission", default=DEFAULT_MISSION)
    i.add_argument("--steps", type=int, default=30)
    i.add_argument("--model", default=DEFAULT_MODEL)
    i.add_argument("--no-llm-skeptic", action="store_true")
    i.set_defaults(fn=cmd_investigate)
    b = sub.add_parser("baseline")
    b.add_argument("--mode", default="synthetic", choices=["live", "synthetic"])
    b.set_defaults(fn=cmd_baseline)
    e = sub.add_parser("eval")
    e.add_argument("--trials", type=int, default=3)
    e.add_argument("--steps", type=int, default=30)
    e.add_argument("--model", default=DEFAULT_MODEL)
    e.set_defaults(fn=cmd_eval)
    d = sub.add_parser("demo")
    d.set_defaults(fn=cmd_demo)
    r = sub.add_parser("report")
    r.add_argument("db")
    r.set_defaults(fn=cmd_report)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
