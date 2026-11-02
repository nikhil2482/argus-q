# ARGUS-Q

ARGUS-Q is an AI agent that investigates the U.S. superconducting quantum computing ecosystem using public records. You give it a mission. It decides what to search, builds a network of organizations and people, follows leads, and writes an assessment. A separate review step checks every finding before it goes into the report.

Every conclusion in the report can be traced three ways:

1. The finding itself, with a confidence level.
2. The reason the agent took each step, recorded at the time it took it.
3. The source records behind the claim, plus what would change the assessment.

## Quick start

```bash
git clone https://github.com/nikhil2482/argus-q.git
cd argus-q
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # add ANTHROPIC_API_KEY and OPENALEX_EMAIL
```

Try it without an API key:

```bash
python run.py demo                 # scripted replay on the fictional test data
streamlit run app.py               # open the dashboard
```

Then run the real agent:

```bash
python run.py eval --trials 3              # score the agent against the baseline
python run.py investigate --mode live      # investigate real public data
```

## Two modes

**Synthetic.** A fictional quantum ecosystem in which every organization and person is invented. It comes with an answer key so the agent can be scored. It also contains traps: normal international collaborations that should not be flagged, a foreign institute whose name is close to a listed one, and an author and a patent inventor who share a common name but may be different people.

**Live.** Real publications from OpenAlex. Patents from PatentsView are added if you have a key, and names are checked against the U.S. Consolidated Screening List if you download it.

## How it works

1. The agent receives a mission and a step budget.
2. It calls tools to search publications and patents, read records, screen organization names, add entities and relationships, and open or close leads.
3. Everything is saved to a SQLite file for that run. Each relationship points to the record it came from, and each action is logged with the agent's stated reason.
4. The agent submits its findings.
5. The review step checks each finding. Findings that pass go into a Markdown report and the dashboard.

## Safeguards

These are enforced in code, not only in the prompt.

* The agent can add an entity only if its name appears in the record it cites. It can add a relationship only if both entities appear there.
* The review step rejects any finding that cites a record the agent never retrieved, names an entity missing from the cited records, or says an organization is listed or sanctioned without an exact or strong screening match.
* Confidence is lowered when two records with the same person's name are treated as one person, and when a high confidence claim rests on a single record.
* An optional second review by the model sees only the claim and its sources, not the agent's reasoning.
* People are never merged on name alone. Organizations are merged only when their names match exactly after cleanup.

## Evaluation

`python run.py eval` runs the agent several times on the synthetic data and compares it with a baseline. The baseline runs a fixed list of searches and flags things by simple rules, with no judgment. Results are saved to `docs/evaluation.md` and shown in the dashboard.

What gets measured:

* **Facts found.** How many of the 5 answer key judgments appear in findings that passed review.
* **False flags.** Findings that treat an ordinary collaborator as a concern.
* **Overclaims.** Identity matches stated with more confidence than the evidence supports.
* **Rejected in review.** Findings the review step removed.

On the synthetic data the baseline finds 2 of 5 facts and raises 5 false flags.

## Optional data

**Patents.** Get a free key at patentsview.org and set `PATENTSVIEW_API_KEY`. PatentsView has renamed fields in the past, so if patent search fails, compare `argus/sources/patentsview.py` with the current API docs.

**Screening list.** Download the Consolidated Screening List CSV from trade.gov and save it as `data/consolidated_screening_list.csv`. Without it, live runs skip screening and say so in the output.

## Files

```
argus/agent.py        agent loop and instructions
argus/tools.py        the agent's tools and source checks
argus/skeptic.py      review of findings
argus/store.py        storage for records, entities, relationships, leads and decisions
argus/sources/        OpenAlex, PatentsView and the synthetic test data
argus/screening.py    name screening
argus/baseline.py     fixed search comparison
argus/evaluate.py     scoring against the answer key
argus/report.py       Markdown report
argus/graph.py        network view
app.py                dashboard
run.py                command line
tests/                tests that run offline
```

## Scope

ARGUS-Q uses only lawful public publication and patent data. It does not collect contact details or private communications. Its reports describe documented relationships and why they matter strategically. They do not accuse anyone of wrongdoing. International research collaboration is common and legal, and the system is tested to make sure it does not treat collaboration alone as a warning sign.
