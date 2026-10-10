"""LinkedIn source (Playwright-driven, public guest endpoints only).

We use LinkedIn's unauthenticated "jobs-guest" endpoints, which return job
cards as HTML without a login. This deliberately avoids automating a sign-in,
which is the part of LinkedIn's ToS most likely to get an account banned.

NOTE: LinkedIn's Terms of Service prohibit automated scraping even of public
pages. This module is intended for personal, low-volume job hunting. It paces
itself politely and does not attempt to defeat bot-detection. If LinkedIn
rate-limits or blocks you, stop and use a different source rather than escalating.
"""
from __future__ import annotations

import random
import time
import urllib.parse
from typing import List

from bs4 import BeautifulSoup

from ..models import Job

GUEST_SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
GUEST_DETAIL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
PAGE_SIZE = 25

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class LinkedInSource:
    name = "linkedin"

    def _search_url(self, cfg: dict, keyword: str, start: int) -> str:
        params = {
            "keywords": keyword,
            "location": cfg.get("location", "United States"),
            "start": start,
        }
        if cfg.get("remote_only", True):
            params["f_WT"] = "2"          # 2 = Remote
        if cfg.get("part_time_only", True):
            params["f_JT"] = "P"          # P = Part-time
        days = cfg.get("posted_within_days")
        if days:
            # f_TPR=r<seconds>: restrict to postings from the last N days.
            params["f_TPR"] = f"r{int(days) * 86400}"
        return f"{GUEST_SEARCH}?{urllib.parse.urlencode(params)}"

    def fetch(self, cfg: dict) -> List[Job]:
        # Imported here so the rest of the package works without Playwright
        # installed (e.g. for unit-testing salary parsing).
        from playwright.sync_api import sync_playwright

        lo, hi = cfg.get("delay_seconds", [2.5, 5.0])
        # Hard cap on how many jobs to collect (0 / None = no cap).
        max_jobs = cfg.get("max_jobs") or 0
        jobs: dict[str, Job] = {}
        # Track (company, title) so the same role reposted across cities only
        # counts once toward max_jobs (LinkedIn duplicates these heavily).
        seen_roles: set[tuple[str, str]] = set()
        dedupe = cfg.get("dedupe", True)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=cfg.get("headless", True))
            ctx = browser.new_context(user_agent=USER_AGENT, locale="en-US")
            page = ctx.new_page()

            for keyword in cfg.get("keywords", ["analyst"]):
                if max_jobs and len(jobs) >= max_jobs:
                    break
                for page_idx in range(cfg.get("max_pages", 4)):
                    url = self._search_url(cfg, keyword, page_idx * PAGE_SIZE)
                    cards = self._scrape_search_page(page, url)
                    if not cards:
                        break  # no more results for this keyword
                    for job in cards:
                        if job.job_id in jobs:
                            continue
                        role_key = (job.company.strip().lower(), job.title.strip().lower())
                        if dedupe and role_key in seen_roles:
                            continue
                        seen_roles.add(role_key)
                        jobs[job.job_id] = job
                    print(f"    collected {len(jobs)} distinct jobs so far")
                    if max_jobs and len(jobs) >= max_jobs:
                        break
                    time.sleep(random.uniform(lo, hi))

            # Trim to the cap before the (slow) per-posting detail fetch.
            selected = list(jobs.values())[:max_jobs] if max_jobs else list(jobs.values())

            if cfg.get("fetch_descriptions", True):
                for i, job in enumerate(selected, 1):
                    print(f"    reading posting {i}/{len(selected)} for salary ...")
                    self._scrape_detail(page, job)
                    time.sleep(random.uniform(lo, hi))

            ctx.close()
            browser.close()

        return selected

    # ---- internals ----------------------------------------------------------

    def _scrape_search_page(self, page, url: str) -> List[Job]:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"  ! search page failed: {e}")
            return []
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        results = []
        for li in soup.select("li"):
            card = li.find("div", class_="base-card") or li.find("div", class_="job-search-card")
            if not card:
                continue
            job = self._parse_card(card)
            if job:
                results.append(job)
        return results

    def _parse_card(self, card) -> Job | None:
        urn = card.get("data-entity-urn", "")
        job_id = urn.split(":")[-1] if urn else ""

        title_el = card.select_one(".base-search-card__title")
        company_el = card.select_one(".base-search-card__subtitle")
        loc_el = card.select_one(".job-search-card__location")
        link_el = card.select_one("a.base-card__full-link") or card.select_one("a")
        date_el = card.select_one("time")

        url = (link_el.get("href", "").split("?")[0] if link_el else "")
        if not job_id and url:
            # .../jobs/view/some-title-1234567890
            tail = url.rstrip("/").split("-")[-1]
            job_id = tail if tail.isdigit() else url

        if not (title_el and url):
            return None

        return Job(
            source=self.name,
            job_id=job_id or url,
            title=title_el.get_text(strip=True),
            company=company_el.get_text(strip=True) if company_el else "",
            location=loc_el.get_text(strip=True) if loc_el else "",
            url=url,
            posted=date_el.get("datetime", "") if date_el else "",
        )

    def _scrape_detail(self, page, job: Job) -> None:
        if not job.job_id or not job.job_id.isdigit():
            return
        url = GUEST_DETAIL.format(job_id=job.job_id)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"  ! detail failed for {job.job_id}: {e}")
            return
        soup = BeautifulSoup(page.content(), "html.parser")

        desc_el = soup.select_one(".show-more-less-html__markup") or soup.select_one(
            ".description__text"
        )
        if desc_el:
            job.description = desc_el.get_text(" ", strip=True)

        # LinkedIn sometimes surfaces a compensation chip.
        salary_el = soup.select_one(".compensation__salary") or soup.select_one(
            ".salary"
        )
        if salary_el:
            job.salary_text = salary_el.get_text(" ", strip=True)

        # Job type / workplace criteria chips.
        for li in soup.select(".description__job-criteria-item"):
            head = li.select_one(".description__job-criteria-subheader")
            val = li.select_one(".description__job-criteria-text")
            if not (head and val):
                continue
            label = head.get_text(strip=True).lower()
            text = val.get_text(strip=True)
            if "employment type" in label:
                job.job_type = text
