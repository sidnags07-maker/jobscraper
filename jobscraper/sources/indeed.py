"""Indeed source (Playwright, best-effort).

WARNING: Indeed runs aggressive bot-detection (Cloudflare / human-verification)
and its ToS prohibits scraping. This module makes a polite, single-browser
attempt with a normal user-agent and NO evasion. It is very likely to hit a
verification wall; when it does, it reports that clearly and returns nothing
rather than trying to defeat the challenge.

Use non-headless (`headless: false`) for the best chance, and keep volume low.
"""
from __future__ import annotations

import random
import time
import urllib.parse
from typing import List

from bs4 import BeautifulSoup

from ..models import Job

SEARCH = "https://www.indeed.com/jobs"
BASE = "https://www.indeed.com"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Phrases that indicate Indeed served a block / verification page.
BLOCK_MARKERS = (
    "verifying you are human",
    "additional verification required",
    "cloudflare",
    "px-captcha",
    "hcaptcha",
    "recaptcha",
    "/challenge",
    "are you a robot",
)


class IndeedSource:
    name = "indeed"

    def _search_url(self, cfg: dict, keyword: str, start: int) -> str:
        params = {"q": keyword, "l": cfg.get("location", "Remote"), "start": start}
        if cfg.get("part_time_only", True):
            params["jt"] = "parttime"
        days = cfg.get("posted_within_days")
        if days:
            params["fromage"] = int(days)
        return f"{SEARCH}?{urllib.parse.urlencode(params)}"

    def fetch(self, cfg: dict) -> List[Job]:
        from playwright.sync_api import sync_playwright

        lo, hi = cfg.get("delay_seconds", [2.5, 5.0])
        jobs: dict[str, Job] = {}
        blocked = False

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=cfg.get("headless", True))
            ctx = browser.new_context(user_agent=USER_AGENT, locale="en-US")
            page = ctx.new_page()

            for keyword in cfg.get("keywords", ["data entry"]):
                for page_idx in range(cfg.get("max_pages", 4)):
                    url = self._search_url(cfg, keyword, page_idx * 10)
                    cards, blocked = self._scrape_search_page(page, url)
                    if blocked:
                        break
                    if not cards:
                        break
                    for job in cards:
                        jobs.setdefault(job.job_id, job)
                    print(f"    collected {len(jobs)} jobs so far")
                    time.sleep(random.uniform(lo, hi))
                if blocked:
                    break

            ctx.close()
            browser.close()

        if blocked:
            print("  ! Indeed served a human-verification / block page. "
                  "Stopping (no evasion attempted). Try headless:false, or use "
                  "linkedin instead.")
        return list(jobs.values())

    # ---- internals ----------------------------------------------------------

    def _scrape_search_page(self, page, url: str):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)  # let any client-side render settle
        except Exception as e:
            print(f"  ! search page failed: {e}")
            return [], False

        html = page.content()
        low = html.lower()
        if any(m in low for m in BLOCK_MARKERS) and "job_seen_beacon" not in low:
            return [], True

        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.job_seen_beacon") or soup.select("[data-jk]")
        results = []
        for card in cards:
            job = self._parse_card(card)
            if job:
                results.append(job)
        return results, False

    def _parse_card(self, card) -> Job | None:
        jk = card.get("data-jk", "")
        title_el = card.select_one("h2.jobTitle span") or card.select_one("h2.jobTitle")
        company_el = card.select_one('[data-testid="company-name"]')
        loc_el = card.select_one('[data-testid="text-location"]')
        link_el = card.select_one("h2.jobTitle a")
        pay_el = card.select_one('[data-testid="attribute_snippet_testid"]') or \
            card.select_one(".salary-snippet-container") or \
            card.select_one(".metadata.salary-snippet-container")

        if not title_el:
            return None

        href = link_el.get("href", "") if link_el else ""
        if href.startswith("/"):
            href = BASE + href
        if not jk and link_el:
            jk = link_el.get("data-jk", "")

        location = loc_el.get_text(strip=True) if loc_el else ""
        job = Job(
            source=self.name,
            job_id=jk or href or title_el.get_text(strip=True),
            title=title_el.get_text(strip=True),
            company=company_el.get_text(strip=True) if company_el else "",
            location=location,
            url=href or BASE,
            workplace="Remote" if "remote" in location.lower() else "",
        )
        if pay_el:
            job.salary_text = pay_el.get_text(" ", strip=True)
        return job
