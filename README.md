# RemoteRadar

*Remote Part-Time Analyst Job Scraper*

A Playwright-driven job scraper that pulls **remote, part-time, analyst-type**
roles and filters them by an **hourly pay threshold**, then writes results to CSV.

## What it does

1. Drives a real browser (Playwright/Chromium) to query LinkedIn's **public,
   no-login** job-search endpoints.
2. Pulls job cards (title, company, location, link, posted date).
3. Optionally opens each posting to read the description and any salary chip.
4. Normalizes pay (hourly / weekly / monthly / yearly) to **USD/hour** and keeps
   only jobs that clear your threshold (or jobs with no listed pay, if you allow).
5. Writes `jobs.csv`.

## ⚠️ Read this first

LinkedIn's Terms of Service **prohibit automated scraping**, even of public
pages. This tool is for **personal, low-volume** job hunting. It:

- uses only **unauthenticated** endpoints (no login, so your account isn't at risk),
- **paces itself** with random delays,
- does **not** try to defeat bot-detection or solve CAPTCHAs.

If LinkedIn rate-limits or blocks your IP, **stop** — don't escalate. The code is
structured so you can add friendlier sources (Remotive, RemoteOK, We Work
Remotely) as drop-in modules under `jobscraper/sources/`.

## Setup

```bash
cd ~/jobscraper
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Configure

Edit `config.yaml` — keywords, location, `min_hourly_usd`, page count, etc.
Set `headless: false` to watch the browser work.

## Run

```bash
python main.py
open jobs.csv
```

## Project layout

```
config.yaml                 your search settings
main.py                     entry point; registers sources
jobscraper/
  models.py                 Job dataclass
  salary.py                 free-text pay -> USD/hour
  filters.py                title + pay filtering
  output.py                 CSV writer
  sources/
    base.py                 Source interface
    linkedin.py             Playwright LinkedIn source
tests/
  test_salary.py            offline unit tests for the parser (python -m tests.test_salary)
```

## Adding a source

Create `jobscraper/sources/yoursite.py` with a class exposing `name` and
`fetch(cfg) -> list[Job]`, then add it to `SOURCES` in `main.py`.
