"""Offline unit tests for salary normalization. Run: python -m pytest -q
(or just `python tests/test_salary.py`)."""
from jobscraper.salary import parse_salary

CASES = [
    # (text, expected_hourly_min, expected_hourly_max_or_None)
    ("Pay: $22.00/hr", 22.0, None),
    ("$20 - $25 an hour", 20.0, 25.0),
    ("Salary: $45,000/year", round(45000 / 2080, 2), None),
    ("$40K - $55K per year", round(40000 / 2080, 2), round(55000 / 2080, 2)),
    ("$3,500 per month", round(3500 / (2080 / 12), 2), None),
    ("Compensation $800/week", round(800 / 40, 2), None),
    ("We have 500+ employees and great culture", None, None),
    ("", None, None),
    # Regression: 401k-match percentages near the word "pay" are NOT wages.
    ("between 6% and 20% of your pay each year", None, None),
    # Range where the second figure drops the leading '$'.
    ("$70,000 to 130,000 per year", round(70000 / 2080, 2), round(130000 / 2080, 2)),
]


def run():
    failures = 0
    for text, exp_lo, exp_hi in CASES:
        lo, hi, _ = parse_salary(text)
        ok = lo == exp_lo and hi == exp_hi
        status = "ok " if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"[{status}] {text!r:45} -> min={lo} max={hi} "
              f"(expected min={exp_lo} max={exp_hi})")
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return failures


# pytest entry points
def test_all_cases():
    assert run() == 0


if __name__ == "__main__":
    raise SystemExit(1 if run() else 0)
