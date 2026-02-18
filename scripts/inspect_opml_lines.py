#!/usr/bin/env python3
"""
Print a window of lines from an OPML file to inspect parse errors.

Example:
  python scripts/inspect_opml_lines.py --path config/caribbean_intel.opml --start 10 --end 30
"""
from __future__ import annotations

import argparse


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="config/caribbean_intel.opml", help="Path to OPML file")
    ap.add_argument("--start", type=int, default=10, help="0-based start line (inclusive)")
    ap.add_argument("--end", type=int, default=30, help="0-based end line (inclusive)")
    args = ap.parse_args()

    with open(args.path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8")
    except Exception:
        text = raw.decode("utf-8", errors="replace")

    lines = text.splitlines()
    start = max(0, args.start)
    end = min(len(lines) - 1, args.end)
    for i in range(start, end + 1):
        print(f"{i + 1:4d}: {lines[i]}")


if __name__ == "__main__":
    main()
