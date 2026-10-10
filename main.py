#!/usr/bin/env python3
"""Remote part-time analyst job scraper.

Usage:
    python main.py                 # uses config.yaml
    python main.py --config my.yaml
"""
from __future__ import annotations

import argparse
import sys

import yaml

from jobscraper.filters import apply_filters
from jobscraper.output import write_csv
from jobscraper.sources.linkedin import LinkedInSource
from jobscraper.sources.indeed import IndeedSource

# Registry of available sources, keyed by name. Pick which to run via the
# `sources:` list in config.yaml (defaults to linkedin).
REGISTRY = {
    "linkedin": LinkedInSource,
    "indeed": IndeedSource,
}


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape remote part-time analyst jobs.")
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()

    cfg = load_config(args.config)

    # Stream progress live instead of buffering until the end.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    selected_names = cfg.get("sources") or ["linkedin"]
    sources = []
    for name in selected_names:
        cls = REGISTRY.get(name)
        if cls is None:
            print(f"  ! unknown source '{name}' (have: {', '.join(REGISTRY)})")
            continue
        sources.append(cls())

    all_jobs = []
    for source in sources:
        print(f"==> Fetching from {source.name} ...")
        try:
            found = source.fetch(cfg)
        except Exception as e:
            print(f"  ! {source.name} failed: {e}")
            continue
        print(f"    got {len(found)} raw jobs")
        all_jobs.extend(found)

    print(f"==> Filtering {len(all_jobs)} jobs "
          f"(title ~ {cfg.get('title_must_include')}, "
          f">= ${cfg.get('min_hourly_usd')}/hr) ...")
    kept = apply_filters(all_jobs, cfg)
    print(f"    {len(kept)} jobs passed filters")

    out = cfg.get("output_csv", "jobs.csv")
    write_csv(kept, out)
    print(f"==> Wrote {len(kept)} jobs to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
