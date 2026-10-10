"""Shared data structures."""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Optional


@dataclass
class Job:
    source: str
    job_id: str
    title: str
    company: str
    location: str
    url: str
    posted: str = ""                       # human string from the card, best-effort
    job_type: str = ""                     # e.g. "Part-time"
    workplace: str = ""                    # e.g. "Remote"
    description: str = ""                   # filled in only if fetch_descriptions
    salary_text: str = ""                  # raw salary string as found on the page
    hourly_min: Optional[float] = None     # parsed, normalized to USD/hour
    hourly_max: Optional[float] = None

    def to_row(self) -> dict:
        d = asdict(self)
        # Keep the CSV readable: drop the (potentially huge) description body.
        d.pop("description", None)
        return d
