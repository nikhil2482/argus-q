"""A scripted stand-in for the Claude client.

Used by the test-suite and by `python run.py demo` so the full pipeline and UI
can be exercised without an API key. It replays a fixed sequence of tool calls
against the SYNTHETIC world only. It is not an agent and its results are not
evidence of agent performance; the README and UI label it as a replay.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field


@dataclass
class _Block:
    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict = field(default_factory=dict)


@dataclass
class _Resp:
    content: list
    stop_reason: str


_ids = itertools.count(1)


def _tu(tool_name: str, reasoning: str, **kw) -> _Block:
    return _Block(type="tool_use", id=f"toolu_{next(_ids)}", name=tool_name, input={**kw, "reasoning": reasoning})


SCRIPT: list[list[_Block]] = [
    [_Block("text", "Orienting: mapping superconducting qubit programs first."),
     _tu("search_publications", "Broad orientation on the core technology to find the main U.S. programs.", query="superconducting qubit processor")],
    [_tu("search_publications", "Superconducting systems all sit inside dilution refrigerators; checking for supplier concentration.", query="dilution refrigerator")],
    [_tu("read_evidence", "This abstract mentions a single qualified vendor; reading the full text to confirm the claim.", evidence_id="W-S03")],
    [_tu("register_entity", "Halvorsen Cryogenics is named as the only qualified vendor but is not yet in the graph.",
         name="Halvorsen Cryogenics", kind="organization", evidence_id="W-S03")],
    [_tu("add_relationship", "W-S03 states Coldline's configuration depends on Halvorsen as the only qualified vendor.",
         src_id="syn:I04", dst_id="agent:halvorsen-cryogenics", rel_type="DEPENDS_ON", evidence_id="W-S03",
         rationale="Halvorsen Cryogenics is currently the only vendor qualified for our 1,000-line wiring configuration")],
    [_tu("add_relationship", "W-S04 shows Meridian's 72-qubit processor housed in a Halvorsen system.",
         src_id="syn:I03", dst_id="agent:halvorsen-cryogenics", rel_type="USES", evidence_id="W-S04",
         rationale="72-qubit processor housed in a Halvorsen LD-1000 dilution refrigerator")],
    [_tu("record_lead", "If one vendor serves most U.S. programs, alternatives matter; testing whether credible alternatives exist.",
         title="Are there qualified alternatives to Halvorsen?", rationale="Single-vendor dependency stated in W-S03",
         entity_ids=["agent:halvorsen-cryogenics"])],
    [_tu("search_publications", "Looking for comparisons of cryostat vendors to test the single-supplier hypothesis.", query="cryostat comparison Arktis")],
    [_tu("close_lead", "W-S05 shows an alternative exists but with long lead times and no high-density wiring.", lead_id=1,
         outcome="Partially refuted: Arktis Cryo exists as an alternative (W-S05) but with >14-month lead times and no high-density wiring option.")],
    [_tu("search_publications", "Dilution refrigerators need helium-3; checking whether input supply is a constraint.", query="helium-3 supply")],
    [_tu("search_publications", "Readout amplifiers are the other specialized component; mapping who builds them.", query="parametric amplifier readout")],
    [_tu("get_entity", "Lena Voss appears with two affiliations on W-S12; checking her relationships.", entity_id="syn:A03")],
    [_tu("screen_entity", "Voss's second affiliation is a foreign institute; screening it.", entity_id="syn:I07")],
    [_tu("expand_entity", "Following Voss's other work to see whether her amplifier designs reach U.S. commercial programs.", entity_id="syn:A03")],
    [_tu("search_publications", "Checking for similarly named institutes that could be confused with the screened one.", query="Eastern Institute quantum")],
    [_tu("screen_entity", "Screening the similarly named institute to avoid a misattribution.", entity_id="syn:I08")],
    [_tu("search_patents", "Checking who holds patents on qubit readout amplifiers.", query="parametric amplifier qubit readout")],
    [_tu("screen_entity", "Screening the foreign assignee of the amplifier patent.", entity_id="syn:asg-shenhai-precision-instruments-co-ltd")],
    [_tu("record_lead", "The inventor shares a name with a Pell Valley author; this needs corroboration, not assumption.",
         title="Is the Shenhai inventor Wei Tan the Pell Valley author Wei Tan?",
         rationale="Same name on P-S01 and W-S01; common name, no shared identifiers.",
         entity_ids=["syn:A09", "syn:inv-wei-tan-P-S01"])],
    [_tu("submit_findings", "Key threads covered: supplier concentration, input scarcity, a screened-institute affiliation, and a screened patent holder.",
         summary="U.S. superconducting quantum programs in this dataset depend on a single qualified dilution-refrigerator vendor and on scarce helium-3. "
                 "A Northgate University researcher holds a concurrent affiliation with a screened foreign institute and her amplifier work feeds a U.S. "
                 "commercial processor. A screened foreign company holds a qubit-readout amplifier patent; whether its inventor is linked to a U.S. lab is unresolved.",
         findings=[
             {"statement": "Halvorsen Cryogenics is the only vendor qualified for Coldline's high-density wiring configuration, and its systems also host "
                           "Meridian Quantum's and Pell Valley's processors, indicating supplier concentration across U.S. programs.",
              "category": "dependency", "confidence": "high", "evidence_ids": ["W-S03", "W-S04", "W-S01"],
              "entity_ids": ["agent:halvorsen-cryogenics", "syn:I04", "syn:I03", "syn:I01"],
              "gaps": "Vendor market share and order backlogs are not in public records; procurement data would change this."},
             {"statement": "Helium-3, required by every dilution refrigerator, has very limited global supply and rising prices already affect testbeds.",
              "category": "dependency", "confidence": "moderate", "evidence_ids": ["W-S18"], "entity_ids": ["syn:I10", "syn:I02"],
              "gaps": "Single source; government He-3 allocation data would strengthen or weaken this."},
             {"statement": "Lena Voss of Northgate University published in 2024 with a concurrent affiliation at the Eastern Institute of Quantum Engineering, "
                           "which is an exact match on the screening list.",
              "category": "foreign_link", "confidence": "moderate", "evidence_ids": ["W-S12"],
              "entity_ids": ["syn:A03", "syn:I02", "syn:I07"],
              "gaps": "The nature and current status of the affiliation are unknown."},
             {"statement": "Voss's parametric-amplifier designs were integrated into a readout chain for Meridian Quantum's commercial processor.",
              "category": "foreign_link", "confidence": "moderate", "evidence_ids": ["W-S13", "W-S12"],
              "entity_ids": ["syn:A03", "syn:I03"], "gaps": "Whether any design information flowed back is not documented."},
             {"statement": "Shenhai Precision Instruments, an exact match on the screening list, holds a patent on a Josephson parametric amplifier for qubit readout.",
              "category": "capability", "confidence": "moderate", "evidence_ids": ["P-S01"],
              "entity_ids": ["syn:asg-shenhai-precision-instruments-co-ltd"],
              "gaps": "Commercial availability of the device is unknown."},
             {"statement": "A Shenhai inventor shares the name Wei Tan with a Pell Valley author; identity is unresolved.",
              "category": "gap", "confidence": "low", "evidence_ids": ["P-S01", "W-S01"],
              "entity_ids": ["syn:inv-wei-tan-P-S01", "syn:A09", "syn:asg-shenhai-precision-instruments-co-ltd"],
              "gaps": "Needs ORCID, address, or co-inventor overlap to resolve."},
         ],
         collection_gaps="Procurement records, export licensing data, and supplier contracts are not publicly available.")],
]


class ScriptedClient:
    """Mimics `anthropic.Anthropic()` for the subset ARGUS-Q uses."""

    def __init__(self, script: list[list[_Block]] | None = None):
        self.script = list(script or SCRIPT)
        self.i = 0
        self.messages = self

    def create(self, **kwargs):
        if "tools" not in kwargs:  # skeptic review call
            return _Resp([_Block("text", '{"support": "supported", "reason": "scripted review"}')], "end_turn")
        blocks = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        return _Resp(blocks, "tool_use")
