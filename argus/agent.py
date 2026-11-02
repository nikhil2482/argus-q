"""The investigator: a Claude tool-use loop that decides what to collect next,
builds the graph, opens and closes leads, and submits an assessment that the
skeptic then checks."""
from __future__ import annotations

import os
from typing import Callable

from .screening import Screener
from .skeptic import review
from .store import Store
from .tools import TOOL_SCHEMAS, Toolkit

DEFAULT_MODEL = os.getenv("ARGUS_MODEL", "claude-sonnet-5-5")

DEFAULT_MISSION = (
    "Identify critical dependencies in the U.S. superconducting quantum computing ecosystem, including "
    "cryogenic infrastructure and readout components, and assess publicly documented links between U.S. "
    "programs and foreign entities of concern. Distinguish verified facts from analytic judgments."
)

SYSTEM_PROMPT = """You are ARGUS-Q, an autonomous intelligence analyst investigating strategic technology ecosystems using only lawful, public information.

You work in a loop: decide what you need to know, use a tool, update your picture, and decide again. You have a limited step budget (each tool call costs one step; steps_remaining is reported in every result). Plan to finish before it runs out.

METHOD
1. Orient: run a few broad searches to map the main organizations and technologies.
2. Focus: pick the most strategically significant threads (concentrated suppliers, scarce inputs, links to entities of concern) and follow them with expand_entity, read_evidence and targeted searches. Open a lead with record_lead whenever you form a hypothesis; close it when you have confirmed, refuted, or exhausted it.
3. Extract: when a record's text names a supplier, technology or partner that is not in the graph, register_entity it and add_relationship with the exact supporting fact as rationale.
4. Screen: screen foreign organizations that appear connected to U.S. programs.
5. Challenge: before submitting, look for alternatives and disconfirming evidence (e.g. other suppliers; whether a similarly named entity is actually the listed one).
6. Submit: call submit_findings with a bottom line and findings.

ANALYTIC STANDARDS (these are checked; violations get findings rejected)
- Every finding cites evidence_ids you actually retrieved and entity_ids that are named in that evidence.
- International research collaboration is normal and is not, by itself, a concern. Only flag foreign links involving entities with an exact or strong screening match, or with specific evidence of a dependency or transfer pathway.
- A weak screening match is a different, similarly named entity unless other evidence proves otherwise. Do not say an entity is listed unless the screening result is exact or strong.
- The same name on two records (e.g. an author and a patent inventor) does not establish the same person. Report it as an unresolved lead or gap with low confidence.
- Confidence: high = multiple independent records agree; moderate = one clear record or several consistent indirect ones; low = plausible but thin.
- Distinguish what the evidence states from what you judge. Say what is unknown and what would change your assessment.
- Never accuse individuals of wrongdoing. Describe documented relationships and why they matter strategically.

Every tool call must include a `reasoning` argument explaining why you chose this action now."""


Event = Callable[[dict], None]


def _blocks_to_dicts(content) -> list[dict]:
    out = []
    for b in content:
        if b.type == "text":
            out.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return out


class Investigator:
    def __init__(self, store: Store, source, screener: Screener, client, model: str = DEFAULT_MODEL,
                 max_steps: int = 30, llm_skeptic: bool = True, on_event: Event | None = None):
        self.store, self.client, self.model = store, client, model
        self.tools = Toolkit(store, source, screener)
        self.tools.max_steps = max_steps
        self.max_steps = max_steps
        self.llm_skeptic = llm_skeptic
        self.on_event = on_event or (lambda e: None)

    def run(self, mission: str = DEFAULT_MISSION) -> dict:
        self.store.set_meta("mission", mission)
        self.store.set_meta("model", self.model)
        self.store.set_meta("kind", "agent")
        messages: list[dict] = [{"role": "user", "content": f"MISSION: {mission}\n\nBegin the investigation."}]
        step = 0
        nudges = 0
        while self.tools.finished is None:
            force = step >= self.max_steps - 1
            kwargs = dict(model=self.model, max_tokens=4096, system=SYSTEM_PROMPT, tools=TOOL_SCHEMAS, messages=messages)
            if force:
                kwargs["tool_choice"] = {"type": "tool", "name": "submit_findings"}
                messages[-1]["content"] = (messages[-1]["content"] if isinstance(messages[-1]["content"], list)
                                           else [{"type": "text", "text": messages[-1]["content"]}]) + \
                    [{"type": "text", "text": "Step budget exhausted. Submit your findings now with what you have."}]
            resp = self.client.messages.create(**kwargs)
            assistant = _blocks_to_dicts(resp.content)
            messages.append({"role": "assistant", "content": assistant})
            for b in assistant:
                if b["type"] == "text" and b["text"].strip():
                    self.on_event({"type": "thought", "step": step, "text": b["text"]})

            tool_uses = [b for b in assistant if b["type"] == "tool_use"]
            if not tool_uses:
                nudges += 1
                if nudges > 3:
                    break
                messages.append({"role": "user", "content": "Continue using tools, or call submit_findings if you are done."})
                continue

            results = []
            for tu in tool_uses:
                step += 1
                self.tools.step = step
                args = dict(tu["input"] or {})
                reasoning = args.pop("reasoning", "")
                out, summary = self.tools.call(tu["name"], args)
                self.store.log_decision(step, tu["name"], args, reasoning, summary)
                self.on_event({"type": "action", "step": step, "tool": tu["name"], "args": args,
                               "reasoning": reasoning, "summary": summary})
                results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": out})
            messages.append({"role": "user", "content": results})
            if step >= self.max_steps + 5:  # hard stop if the model ignores the forced submit
                break

        return self.finish()

    def finish(self) -> dict:
        sub = self.tools.finished or {"summary": "Investigation ended without a submitted assessment.",
                                      "findings": [], "collection_gaps": ""}
        self.on_event({"type": "review", "count": len(sub["findings"])})
        reviewed = review(sub["findings"], self.store, self.client if self.llm_skeptic else None, self.model)
        self.store.save_findings(reviewed)
        self.store.set_meta("summary", sub["summary"])
        self.store.set_meta("collection_gaps", sub.get("collection_gaps", ""))
        self.store.set_meta("steps_used", self.tools.step)
        self.on_event({"type": "done", "findings": reviewed})
        return {"summary": sub["summary"], "findings": reviewed, "stats": self.store.stats()}
