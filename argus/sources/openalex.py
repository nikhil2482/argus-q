"""OpenAlex connector (https://docs.openalex.org). Free, no account required;
set OPENALEX_EMAIL for the polite pool and OPENALEX_API_KEY if you have one."""
from __future__ import annotations

import os
import time

import requests

BASE = "https://api.openalex.org"
SELECT = "id,doi,title,publication_year,authorships,abstract_inverted_index"


def _short(oa_id: str | None) -> str | None:
    return oa_id.rsplit("/", 1)[-1] if oa_id else None


def _abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    slots: dict[int, str] = {}
    for word, positions in inv.items():
        for p in positions:
            slots[p] = word
    return " ".join(slots[i] for i in sorted(slots))


def normalize_work(w: dict) -> dict:
    wid = _short(w.get("id"))
    authors = []
    for au in w.get("authorships", []) or []:
        a = au.get("author") or {}
        if not a.get("id"):
            continue
        insts = [{"id": f"oa:{_short(i.get('id'))}", "name": i.get("display_name"),
                  "country": i.get("country_code"), "type": i.get("type")}
                 for i in au.get("institutions", []) or [] if i.get("id")]
        authors.append({"id": f"oa:{_short(a['id'])}", "name": a.get("display_name"), "institutions": insts})
    return {"id": f"oa:{wid}", "source": "openalex", "kind": "work",
            "url": w.get("doi") or w.get("id"), "title": w.get("title") or "(untitled)",
            "year": w.get("publication_year"), "text": _abstract(w.get("abstract_inverted_index")),
            "authors": authors}


class OpenAlexSource:
    name = "openalex"

    def __init__(self, email: str | None = None, api_key: str | None = None, timeout: int = 30):
        self.email = email or os.getenv("OPENALEX_EMAIL")
        self.api_key = api_key or os.getenv("OPENALEX_API_KEY")
        self.timeout = timeout
        self.session = requests.Session()

    def _get(self, params: dict) -> list[dict]:
        params = {**params, "select": SELECT}
        if self.email:
            params["mailto"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key
        for attempt in range(3):
            r = self.session.get(f"{BASE}/works", params=params, timeout=self.timeout)
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return [normalize_work(w) for w in r.json().get("results", [])]
        r.raise_for_status()
        return []

    def search_works(self, query: str, limit: int = 10) -> list[dict]:
        return self._get({"search": query, "per-page": min(limit, 50)})

    def works_for_entity(self, entity_id: str, name: str = "", limit: int = 15) -> list[dict]:
        short = entity_id.split(":", 1)[-1]
        if entity_id.startswith("oa:I"):
            flt = f"authorships.institutions.id:{short}"
        elif entity_id.startswith("oa:A"):
            flt = f"authorships.author.id:{short}"
        else:
            return self.search_works(name or short, limit)
        return self._get({"filter": flt, "sort": "publication_date:desc", "per-page": min(limit, 50)})
