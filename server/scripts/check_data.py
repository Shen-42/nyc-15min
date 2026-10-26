"""Sanity check for the downloaded data, used by the monthly refresh job (card 8).

    python scripts/check_data.py --snapshot before.json   # save today's counts
    python scripts/check_data.py --compare before.json    # after rebuilding

--compare fails (exit code 1) if any count shrank by more than MAX_DROP, or
fell below its floor. A sharp drop usually means a download came back
incomplete, and committing it would quietly break the live site.
It also writes a results table to the GitHub Actions run summary.
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# A count may shrink by at most this share between refreshes.
MAX_DROP = 0.15

# Hard floors, whatever the previous counts were.
FLOORS = {
    "graph nodes": 30_000,
    "graph segments": 45_000,
    "subway stations": 140,  # Manhattan has about 150
    "lakes and ponds": 8,
}

LABELS = {
    "grocery": "groceries",
    "pharmacy": "pharmacies",
    "clinic": "doctors and clinics",
    "park": "parks",
    "school": "schools",
    "subway": "subway stations",
}


def current_counts():
    graph = json.loads((DATA / "walk_graph.json").read_text())
    water = json.loads((DATA / "water.json").read_text())
    places = json.loads((DATA / "amenities.json").read_text())
    by_category = Counter(p["category"] for p in places)
    counts = {
        "graph nodes": len(graph["nodes"]),
        "graph segments": len(graph["edges"]),
        "lakes and ponds": len(water),
    }
    for category, label in LABELS.items():
        counts[label] = by_category[category]
    ramps_file = DATA / "ramps.json"
    if ramps_file.exists():
        meta = json.loads(ramps_file.read_text())["meta"]
        counts["curb ramps"] = meta["ramps"]
    return counts


def write_summary(lines):
    print("\n".join(lines))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write("\n".join(lines) + "\n")


def compare(before):
    after = current_counts()
    problems = []
    lines = ["## Data refresh check", "", "| Data | Before | After | Change | |", "| --- | ---: | ---: | ---: | --- |"]
    for name, new in after.items():
        old = before.get(name)
        change = f"{(new - old) / old:+.1%}" if old else "new"
        ok = True
        if old and new < old * (1 - MAX_DROP):
            problems.append(f"{name} dropped from {old} to {new}")
            ok = False
        if name in FLOORS and new < FLOORS[name]:
            problems.append(f"{name} is {new}, below the floor of {FLOORS[name]}")
            ok = False
        lines.append(f"| {name} | {old if old is not None else '–'} | {new} | {change} | {'ok' if ok else 'FAILED'} |")

    lines.append("")
    if problems:
        lines.append("**Not committed.** " + "; ".join(problems) + ".")
    else:
        lines.append("All counts look normal.")
    write_summary(lines)
    return not problems


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--snapshot", help="save the current counts to this file")
    group.add_argument("--compare", help="compare the current counts with this saved file")
    args = parser.parse_args()

    if args.snapshot:
        Path(args.snapshot).write_text(json.dumps(current_counts(), indent=2))
        print(f"Saved counts to {args.snapshot}")
        return
    ok = compare(json.loads(Path(args.compare).read_text()))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
