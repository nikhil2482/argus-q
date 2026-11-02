from __future__ import annotations

from .openalex import OpenAlexSource
from .patentsview import PatentsViewSource
from .synthetic import SyntheticSource


class LiveSource:
    """Real public data: OpenAlex for publications, PatentsView for patents."""
    name = "live"

    def __init__(self):
        self.works = OpenAlexSource()
        self.patents = PatentsViewSource()

    @property
    def patents_enabled(self) -> bool:
        return self.patents.patents_enabled

    def search_works(self, query, limit=10):
        return self.works.search_works(query, limit)

    def works_for_entity(self, entity_id, name="", limit=15):
        return self.works.works_for_entity(entity_id, name, limit)

    def search_patents(self, query, limit=10):
        return self.patents.search_patents(query, limit)


def get_source(mode: str):
    if mode == "synthetic":
        return SyntheticSource()
    if mode == "live":
        return LiveSource()
    raise ValueError(f"unknown mode {mode!r} (use 'synthetic' or 'live')")
