"""USPTO PatentsView Search API connector (optional).

Requires a free API key in PATENTSVIEW_API_KEY (request one at
https://patentsview.org). The API's field names have changed over time; if
requests fail, check the current docs and adjust FIELDS / _normalize below.
"""
from __future__ import annotations

import os
import re

import requests

URL = "https://search.patentsview.org/api/v1/patent/"
FIELDS = ["patent_id", "patent_title", "patent_date", "patent_abstract",
          "assignees.assignee_organization", "assignees.assignee_country",
          "inventors.inventor_name_first", "inventors.inventor_name_last"]


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _normalize(p: dict) -> dict:
    pid = p.get("patent_id")
    assignees = []
    for a in p.get("assignees") or []:
        org = a.get("assignee_organization")
        if org:
            assignees.append({"id": f"pv:asg-{_slug(org)}", "name": org, "country": a.get("assignee_country")})
    inventors = []
    for i in p.get("inventors") or []:
        name = " ".join(x for x in [i.get("inventor_name_first"), i.get("inventor_name_last")] if x)
        if name:
            # Inventor ids are scoped to the patent: same name != same person.
            inventors.append({"id": f"pv:inv-{_slug(name)}-{pid}", "name": name})
    return {"id": f"pv:{pid}", "source": "patentsview", "kind": "patent",
            "url": f"https://patents.google.com/patent/US{pid}", "title": p.get("patent_title") or "",
            "year": int(str(p.get("patent_date") or "0")[:4] or 0) or None,
            "text": p.get("patent_abstract") or "", "assignees": assignees, "inventors": inventors}


class PatentsViewSource:
    name = "patentsview"

    def __init__(self, api_key: str | None = None, timeout: int = 30):
        self.api_key = api_key or os.getenv("PATENTSVIEW_API_KEY")
        self.timeout = timeout

    @property
    def patents_enabled(self) -> bool:
        return bool(self.api_key)

    def search_patents(self, query: str, limit: int = 10) -> list[dict]:
        if not self.api_key:
            raise RuntimeError("Patent search is not configured (set PATENTSVIEW_API_KEY).")
        body = {"q": {"_or": [{"_text_any": {"patent_title": query}},
                              {"_text_any": {"patent_abstract": query}}]},
                "f": FIELDS, "o": {"size": min(limit, 50)}}
        r = requests.post(URL, json=body, headers={"X-Api-Key": self.api_key}, timeout=self.timeout)
        r.raise_for_status()
        return [_normalize(p) for p in r.json().get("patents", []) or []]
