"""CSV writer."""
from __future__ import annotations

import csv
from typing import List

from .models import Job

COLUMNS = [
    "source", "title", "company", "location", "workplace", "job_type",
    "hourly_min", "hourly_max", "salary_text", "posted", "url", "job_id",
]


def write_csv(jobs: List[Job], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for job in jobs:
            writer.writerow(job.to_row())
