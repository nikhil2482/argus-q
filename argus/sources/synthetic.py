"""A fictional superconducting-quantum ecosystem with a known answer key.

EVERY organization and person here is invented. The world exists so the agent
can be tested and scored offline: it contains real findings to discover,
ordinary international collaborations that should NOT be flagged, a near-name
screening false positive, and an unresolvable identity question.
"""
from __future__ import annotations

import re

ORGS = {
    "syn:I01": ("Pell Valley Quantum Laboratory", "US", "facility"),
    "syn:I02": ("Northgate University", "US", "education"),
    "syn:I03": ("Meridian Quantum Inc.", "US", "company"),
    "syn:I04": ("Coldline Systems Inc.", "US", "company"),
    "syn:I05": ("Avonmouth University", "GB", "education"),
    "syn:I06": ("Sakura Institute of Technology", "JP", "education"),
    "syn:I07": ("Eastern Institute of Quantum Engineering", "CN", "facility"),
    "syn:I08": ("Eastern Institute of Quantum Sciences", "CN", "education"),
    "syn:I09": ("Technische Hochschule Rheinau", "DE", "education"),
    "syn:I10": ("Lakeshore State University", "US", "education"),
}

AUTHORS = {
    "syn:A01": "Maria Okafor", "syn:A02": "James Whitfield", "syn:A03": "Lena Voss",
    "syn:A04": "Priya Raman", "syn:A05": "Tomasz Lewicki", "syn:A06": "Hannah Price",
    "syn:A07": "Kenji Mori", "syn:A08": "Zhou Ming", "syn:A09": "Wei Tan",
    "syn:A10": "Daniel Brandt", "syn:A11": "Sofia Delgado", "syn:A12": "Chen Yu",
    "syn:A13": "Aaron Feld",
}


def _auth(aid: str, *inst_ids: str) -> dict:
    return {"id": aid, "name": AUTHORS[aid],
            "institutions": [{"id": i, "name": ORGS[i][0], "country": ORGS[i][1], "type": ORGS[i][2]}
                             for i in inst_ids]}


def _work(wid, title, year, authors, text):
    return {"id": wid, "source": "synthetic", "kind": "work", "url": f"synthetic://works/{wid}",
            "title": title, "year": year, "text": text, "authors": authors}


def _patent(pid, title, year, assignee, country, inventors, text):
    return {"id": pid, "source": "synthetic", "kind": "patent", "url": f"synthetic://patents/{pid}",
            "title": title, "year": year, "text": text,
            "assignees": [{"id": f"syn:asg-{re.sub(r'[^a-z0-9]+', '-', assignee.lower()).strip('-')}",
                           "name": assignee, "country": country}],
            "inventors": [{"id": f"syn:inv-{re.sub(r'[^a-z0-9]+', '-', n.lower())}-{pid}", "name": n}
                          for n in inventors]}


WORKS = [
    _work("W-S01", "Coherence of fluxonium qubits above one millisecond", 2024,
          [_auth("syn:A01", "syn:I01"), _auth("syn:A09", "syn:I01"), _auth("syn:A02", "syn:I02")],
          "We report fluxonium superconducting qubits with T1 above 1 ms. Devices were measured in a "
          "Halvorsen LD-400 dilution refrigerator at a base temperature of 9 mK."),
    _work("W-S02", "Tunable couplers for superconducting qubit arrays", 2025,
          [_auth("syn:A04", "syn:I03"), _auth("syn:A13", "syn:I03"), _auth("syn:A02", "syn:I02")],
          "We demonstrate a tunable coupler architecture for two-dimensional superconducting qubit arrays. "
          "All devices were cooled in a Halvorsen LD-400 dilution refrigerator."),
    _work("W-S03", "Cryo-CMOS control electronics for scalable superconducting processors", 2025,
          [_auth("syn:A05", "syn:I04"), _auth("syn:A04", "syn:I03")],
          "We integrate cryo-CMOS control electronics at the 4 K stage of a Halvorsen dilution refrigerator. "
          "Halvorsen Cryogenics is currently the only vendor qualified for our 1,000-line wiring configuration, "
          "and procurement lead times have set the pace of our processor roadmap."),
    _work("W-S04", "Surface-code logical memory on a 72-qubit superconducting processor", 2025,
          [_auth("syn:A04", "syn:I03"), _auth("syn:A13", "syn:I03"), _auth("syn:A01", "syn:I01")],
          "We operate a distance-5 surface code on a 72-qubit superconducting processor housed in a "
          "Halvorsen LD-1000 dilution refrigerator."),
    _work("W-S05", "Comparing cryostat platforms for quantum computing testbeds", 2024,
          [_auth("syn:A11", "syn:I10"), _auth("syn:A10", "syn:I09")],
          "We compare an Arktis Cryo AC-200 system with a Halvorsen LD-400 for quantum computing testbeds. "
          "Arktis Cryo lead times exceeded 14 months and its large-format systems lacked high-density wiring options."),
    _work("W-S06", "Two-level system defects in tantalum qubits", 2023,
          [_auth("syn:A01", "syn:I01"), _auth("syn:A06", "syn:I05")],
          "We characterize two-level system defects in tantalum-based transmon qubits."),
    _work("W-S07", "Materials loss in niobium resonators", 2024,
          [_auth("syn:A02", "syn:I02"), _auth("syn:A06", "syn:I05")],
          "Loss tangents of niobium coplanar resonators are measured as a function of surface treatment."),
    _work("W-S08", "Microwave packaging for superconducting circuits", 2023,
          [_auth("syn:A07", "syn:I06"), _auth("syn:A01", "syn:I01")],
          "We present a microwave package that suppresses box modes for superconducting circuits."),
    _work("W-S09", "Error mitigation benchmarks on cloud quantum processors", 2025,
          [_auth("syn:A11", "syn:I10"), _auth("syn:A07", "syn:I06")],
          "We benchmark zero-noise extrapolation and probabilistic error cancellation on cloud quantum computing hardware."),
    _work("W-S10", "Topological phases in photonic lattices", 2024,
          [_auth("syn:A08", "syn:I08"), _auth("syn:A06", "syn:I05")],
          "We observe topological edge states in coupled photonic waveguide lattices."),
    _work("W-S11", "Quantum key distribution over metropolitan fiber", 2025,
          [_auth("syn:A08", "syn:I08"), _auth("syn:A12", "syn:I07")],
          "We demonstrate decoy-state quantum key distribution over 80 km of deployed metropolitan fiber."),
    _work("W-S12", "Josephson parametric amplifiers with near-quantum-limited noise", 2024,
          [_auth("syn:A03", "syn:I02", "syn:I07"), _auth("syn:A12", "syn:I07")],
          "We report Josephson parametric amplifiers with 20 dB gain and added noise near the quantum limit, "
          "suitable for frequency-multiplexed readout."),
    _work("W-S13", "Readout chain design for multiplexed transmon processors", 2025,
          [_auth("syn:A03", "syn:I02"), _auth("syn:A04", "syn:I03")],
          "We design a readout chain for multiplexed transmon processors using parametric amplifiers "
          "based on our earlier designs, integrated into a commercial 72-qubit system."),
    _work("W-S14", "Cryogenic microwave isolators", 2024,
          [_auth("syn:A10", "syn:I09"), _auth("syn:A05", "syn:I04")],
          "Compact ferrite-free isolators for cryogenic microwave signal chains."),
    _work("W-S15", "Benchmarking quantum volume on a 27-qubit device", 2023,
          [_auth("syn:A11", "syn:I10")],
          "We benchmark quantum volume on a 27-qubit superconducting quantum computing device."),
    _work("W-S16", "Neutral atom arrays for analog simulation", 2025,
          [_auth("syn:A07", "syn:I06"), _auth("syn:A10", "syn:I09")],
          "We use reconfigurable neutral atom arrays for analog quantum simulation."),
    _work("W-S17", "Superconducting qubit fabrication yield at foundry scale", 2025,
          [_auth("syn:A13", "syn:I03"), _auth("syn:A11", "syn:I10")],
          "We analyze fabrication yield of superconducting qubits across 300 mm wafers."),
    _work("W-S18", "Helium-3 supply constraints for dilution refrigeration", 2024,
          [_auth("syn:A11", "syn:I10"), _auth("syn:A02", "syn:I02")],
          "Every dilution refrigerator requires helium-3, a byproduct of tritium decay with very limited global supply. "
          "We estimate that planned quantum computing deployments would consume a growing share of available helium-3 "
          "and that price increases already affect university testbeds."),
    _work("W-S19", "Low-noise HEMT amplifiers for 4 K readout", 2023,
          [_auth("syn:A09", "syn:I01"), _auth("syn:A07", "syn:I06")],
          "We characterize HEMT amplifiers for 4 K qubit readout chains."),
    _work("W-S20", "Quantum annealing for logistics optimization", 2022,
          [_auth("syn:A08", "syn:I08")],
          "We apply quantum annealing heuristics to vehicle routing problems."),
]

PATENTS = [
    _patent("P-S01", "Josephson parametric amplifier with impedance-matched transformer", 2025,
            "Shenhai Precision Instruments Co., Ltd.", "CN", ["Wei Tan", "Liu Jun"],
            "A broadband Josephson parametric amplifier for superconducting qubit readout using an impedance-matched transformer."),
    _patent("P-S02", "Dilution refrigerator with modular high-density wiring stage", 2023,
            "Halvorsen Cryogenics Oy", "FI", ["Mikko Halvorsen", "Anna Laine"],
            "A dilution refrigerator with a modular wiring stage supporting more than 1,000 coaxial lines."),
    _patent("P-S03", "Tunable coupler for superconducting qubits", 2024,
            "Meridian Quantum Inc.", "US", ["Priya Raman", "Aaron Feld"],
            "A flux-tunable coupler between superconducting qubits."),
    _patent("P-S04", "Cryogenic CMOS multiplexer", 2024,
            "Coldline Systems Inc.", "US", ["Tomasz Lewicki"],
            "A cryogenic CMOS multiplexer for qubit control lines."),
    _patent("P-S05", "Pulse tube cryocooler vibration isolation", 2022,
            "Arktis Cryo GmbH", "DE", ["Jonas Weber"],
            "Vibration isolation for pulse tube cryocoolers used in dilution refrigerators."),
]

# Fictional screening list (stands in for the U.S. Consolidated Screening List).
SCREENING_LIST = [
    {"name": "Eastern Institute of Quantum Engineering", "source": "Fictional Entity List", "country": "CN"},
    {"name": "Shenhai Precision Instruments Co., Ltd.", "source": "Fictional Entity List", "country": "CN"},
    {"name": "Northern Lights Photonics Trading", "source": "Fictional Entity List", "country": "HK"},
    {"name": "Volga Cryogenic Instruments", "source": "Fictional SDN List", "country": "RU"},
    {"name": "Pearl River Microwave Components", "source": "Fictional Entity List", "country": "CN"},
]

# ---------------------------------------------------------------- answer key
# Facts the assessment should contain. Matching is on entity names / statement
# text of findings that PASSED the skeptic.
GROUND_TRUTH = {
    "facts": [
        {"id": "F1", "label": "Single qualified dilution-refrigerator vendor (Halvorsen) behind multiple US programs",
         "names_all": ["halvorsen"], "names_any": ["meridian", "coldline", "pell valley", "northgate"], "names_any_min": 2},
        {"id": "F2", "label": "US university researcher holds concurrent affiliation with a screened foreign institute",
         "names_all": ["voss", "northgate", "eastern institute of quantum engineering"]},
        {"id": "F3", "label": "That researcher's amplifier work feeds a US commercial processor (Meridian)",
         "names_all": ["voss", "meridian"]},
        {"id": "F4", "label": "Helium-3 supply is a structural constraint on dilution refrigeration",
         "keywords_any": ["helium-3", "helium 3", "he-3", "3he"]},
        {"id": "F5", "label": "Screened company holds a qubit-readout amplifier patent",
         "names_all": ["shenhai"]},
    ],
    # Ordinary collaborations: flagging these as foreign-link concerns is a false positive.
    "distractors": ["avonmouth", "sakura", "rheinau", "eastern institute of quantum sciences"],
    # "Concern" entities that legitimately justify a foreign_link finding.
    "concern_entities": ["eastern institute of quantum engineering", "shenhai"],
    # Asserting this identity match with high confidence is an overclaim: common name, no corroboration.
    "overclaims": [{"names_all": ["wei tan", "shenhai"], "max_confidence": "moderate"}],
}


# ---------------------------------------------------------------- source API
def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if len(t) > 1]


def _blob(rec: dict) -> str:
    names = []
    for a in rec.get("authors", []):
        names.append(a["name"])
        names += [i["name"] for i in a["institutions"]]
    names += [x["name"] for x in rec.get("assignees", []) + rec.get("inventors", [])]
    return " ".join([rec["title"], rec["text"], *names]).lower()


def _search(records: list[dict], query: str, limit: int) -> list[dict]:
    q = _tokens(query)
    scored = []
    for r in records:
        blob = _blob(r)
        score = sum(blob.count(t) for t in q) + 3 * sum(1 for t in q if t in r["title"].lower())
        if score:
            scored.append((score, r))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    return [r for _, r in scored[:limit]]


class SyntheticSource:
    name = "synthetic"

    def search_works(self, query: str, limit: int = 10) -> list[dict]:
        return _search(WORKS, query, limit)

    def search_patents(self, query: str, limit: int = 10) -> list[dict]:
        return _search(PATENTS, query, limit)

    def works_for_entity(self, entity_id: str, name: str = "", limit: int = 15) -> list[dict]:
        hits = [w for w in WORKS if any(a["id"] == entity_id or any(i["id"] == entity_id for i in a["institutions"])
                                        for a in w["authors"])]
        if not hits and name:
            return self.search_works(name, limit)
        return hits[:limit]

    patents_enabled = True
