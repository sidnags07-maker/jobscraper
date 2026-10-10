"""Source interface. Every site we scrape implements `fetch`."""
from __future__ import annotations

from typing import List, Protocol

from ..models import Job


class Source(Protocol):
    name: str

    def fetch(self, cfg: dict) -> List[Job]:
        """Return raw jobs (unfiltered). Filtering happens centrally."""
        ...
