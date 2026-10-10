"""Central filtering: title relevance + pay threshold."""
from __future__ import annotations

from typing import List

from .models import Job
from .salary import parse_salary


def _enrich_salary(job: Job) -> None:
    """Populate hourly_min/max from salary_text first, then description."""
    for text in (job.salary_text, job.description):
        lo, hi, snippet = parse_salary(text)
        if lo is not None:
            job.hourly_min, job.hourly_max = lo, hi
            if not job.salary_text:
                job.salary_text = snippet
            return


def _title_ok(job: Job, must_include: List[str]) -> bool:
    if not must_include:
        return True
    title = job.title.lower()
    return any(word.lower() in title for word in must_include)


REMOTE_HINTS = ("remote", "work from home", "work-from-home", "wfh", "telecommute")


def _looks_remote(job: Job) -> bool:
    """Positive remote signal from any field we have. LinkedIn's remote search
    filter is loose, so we confirm against the actual posting text."""
    hay = " ".join([job.title, job.location, job.workplace, job.description]).lower()
    return any(h in hay for h in REMOTE_HINTS)


def _pay_ok(job: Job, min_hourly: float, keep_if_unknown: bool) -> bool:
    if job.hourly_min is None and job.hourly_max is None:
        return keep_if_unknown
    # Compare against the top of the advertised range, if present.
    top = job.hourly_max if job.hourly_max is not None else job.hourly_min
    return top is not None and top >= min_hourly


def _dedupe(jobs: List[Job], max_per_company: int) -> List[Job]:
    """Collapse identical (company, title) repeats and optionally cap how many
    jobs any single company may contribute."""
    seen_keys: set[tuple[str, str]] = set()
    per_company: dict[str, int] = {}
    out = []
    for job in jobs:
        key = (job.company.strip().lower(), job.title.strip().lower())
        if key in seen_keys:
            continue
        company = job.company.strip().lower()
        if max_per_company and per_company.get(company, 0) >= max_per_company:
            continue
        seen_keys.add(key)
        per_company[company] = per_company.get(company, 0) + 1
        out.append(job)
    return out


def apply_filters(jobs: List[Job], cfg: dict) -> List[Job]:
    must_include = cfg.get("title_must_include", [])
    min_hourly = float(cfg.get("min_hourly_usd", 0))
    keep_unknown = bool(cfg.get("keep_if_no_salary", True))

    strict_pt = bool(cfg.get("strict_part_time", False))
    strict_remote = bool(cfg.get("strict_remote", False))

    kept = []
    for job in jobs:
        _enrich_salary(job)
        if not _title_ok(job, must_include):
            continue
        if not _pay_ok(job, min_hourly, keep_unknown):
            continue
        # LinkedIn's part-time search filter is only a hint; enforce it for real
        # using the employment-type read from each posting. Drop anything we can
        # positively identify as not part-time (unknowns are kept).
        if strict_pt and job.job_type and "part" not in job.job_type.lower():
            continue
        # Likewise, confirm the role is actually remote (city-located on-site
        # jobs leak through LinkedIn's remote filter).
        if strict_remote and not _looks_remote(job):
            continue
        kept.append(job)

    if cfg.get("dedupe", True):
        kept = _dedupe(kept, int(cfg.get("max_per_company", 0) or 0))
    return kept
