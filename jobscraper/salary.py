"""Best-effort salary extraction and normalization to USD/hour.

Job postings express pay in wildly inconsistent ways. We try to pull one or two
dollar figures plus a time unit out of free text, then convert to an hourly
rate so a single threshold (e.g. $20/hr) can filter everything.

Assumes full-time equivalence of 2080 hours/year (40h * 52w) when annualizing.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

HOURS_PER_YEAR = 2080.0
HOURS_PER_MONTH = HOURS_PER_YEAR / 12.0
HOURS_PER_WEEK = 40.0

# Matches things like $20, $20.50, $1,500, $45k, 45K
_MONEY = re.compile(r"\$?\s*(\d[\d,]*\.?\d*)\s*(k\b)?", re.IGNORECASE)


def _to_float(num: str, k_suffix: Optional[str]) -> Optional[float]:
    try:
        val = float(num.replace(",", ""))
    except ValueError:
        return None
    if k_suffix:
        val *= 1000.0
    return val


def _unit_to_hourly(value: float) -> float:
    """Heuristic: bare numbers' unit is inferred by the caller; this just maps."""
    return value


def _detect_period(text: str) -> str:
    """Return one of: hour, week, month, year, or '' if unknown."""
    t = text.lower()
    if re.search(r"\b(per\s*hour|/\s*hr|/\s*hour|an?\s*hour|hourly)\b", t):
        return "hour"
    if re.search(r"\b(per\s*week|/\s*wk|/\s*week|weekly)\b", t):
        return "week"
    if re.search(r"\b(per\s*month|/\s*mo|/\s*month|monthly)\b", t):
        return "month"
    if re.search(r"\b(per\s*year|/\s*yr|/\s*year|annual|annually|year)\b", t):
        return "year"
    return ""


def _annualish_to_hourly(value: float, period: str) -> Optional[float]:
    if period == "hour":
        return value
    if period == "week":
        return value / HOURS_PER_WEEK
    if period == "month":
        return value / HOURS_PER_MONTH
    if period == "year":
        return value / HOURS_PER_YEAR
    return None


def parse_salary(text: str) -> Tuple[Optional[float], Optional[float], str]:
    """Extract (hourly_min, hourly_max, matched_snippet) from free text.

    Returns (None, None, "") when nothing salary-like is found.
    """
    if not text:
        return None, None, ""

    # Look at a window around the first '$' or pay keyword to avoid grabbing
    # unrelated numbers (like "500+ employees").
    anchor = None
    m = re.search(r"\$", text)
    if m:
        anchor = m.start()
    else:
        kw = re.search(r"\b(salary|compensation|pay|wage|rate)\b", text, re.IGNORECASE)
        if kw:
            anchor = kw.start()
    if anchor is None:
        return None, None, ""

    window = text[max(0, anchor - 20): anchor + 120]

    # If we anchored on a keyword (no '$' in the text at all), the window is much
    # more likely to contain stray numbers (percentages, counts). Require a '$'
    # in the window to proceed, which kills most false positives.
    if "$" not in window:
        return None, None, ""

    nums = []
    for mm in _MONEY.finditer(window):
        # Skip percentages, e.g. "6% and 20% of your pay" (benefits, not wages).
        if window[mm.end(): mm.end() + 1] == "%":
            continue
        val = _to_float(mm.group(1), mm.group(2))
        if val is None or val < 5:
            continue
        # Trust a figure only if it's money-like: prefixed with '$', has a 'k'
        # suffix, or is large enough (>=1000) to be a salary range value. This
        # drops stray small bare numbers (headcounts, percentages, years).
        has_dollar = "$" in mm.group(0)
        if not (has_dollar or mm.group(2) or val >= 1000):
            continue
        nums.append(val)
    if not nums:
        return None, None, ""

    period = _detect_period(window)
    # If two figures look like a range, use the first two; else single value.
    lo = nums[0]
    hi = nums[1] if len(nums) > 1 else None

    # Infer period when not stated: small numbers (<200) are almost certainly
    # hourly; large ones annual.
    if not period:
        period = "hour" if lo < 200 else "year"

    h_lo = _annualish_to_hourly(lo, period)
    h_hi = _annualish_to_hourly(hi, period) if hi is not None else None

    if h_lo is None:
        return None, None, ""
    if h_hi is not None and h_hi < h_lo:
        h_lo, h_hi = h_hi, h_lo

    snippet = window.strip()
    snippet = re.sub(r"\s+", " ", snippet)[:80]
    return (round(h_lo, 2), round(h_hi, 2) if h_hi else None, snippet)
