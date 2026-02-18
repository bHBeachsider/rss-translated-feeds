#!/usr/bin/env python3
"""
Safely sanitize an OPML file so it parses as XML.

Actions:
- Creates a .bak backup.
- Removes C0 control chars (except \n, \r, \t).
- Escapes bare '&' not part of valid XML entities.
- Writes a sanitized file.
- Attempts to parse the sanitized file and prints context on failure.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET


def sanitize_text(text: str) -> str:
    # Remove C0 control chars except legal whitespace
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
    # Escape bare ampersands not part of a valid XML entity
    text = re.sub(
        r"&(?!(?:amp|lt|gt|quot|apos);|#[0-9]+;|#x[0-9A-Fa-f]+;)", "&amp;", text
    )
    return text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="config/caribbean_intel.opml", help="Path to OPML file")
    ap.add_argument(
        "--out",
        default="config/caribbean_intel.sanitized.opml",
        help="Output path for sanitized OPML",
    )
    args = ap.parse_args()

    if not os.path.exists(args.path):
        print(f"ERROR: file not found: {args.path}")
        sys.exit(1)

    bak = args.path + ".bak"
    shutil.copy2(args.path, bak)
    print(f"Backup created: {bak}")

    raw = open(args.path, "rb").read()
    try:
        text = raw.decode("utf-8")
    except Exception:
        text = raw.decode("utf-8", errors="replace")

    text = sanitize_text(text)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Sanitized file written: {args.out}")

    # Sanity-check parse
    try:
        ET.parse(args.out)
        print("Sanitized OPML parses OK.")
    except Exception as e:
        print("Sanitized OPML still fails to parse:", e)
        m = re.search(r"line (\d+), column (\d+)", str(e))
        if m:
            ln = int(m.group(1))
            lines = text.splitlines()
            start = max(0, ln - 5)
            end = min(len(lines), ln + 5)
            print("Context:")
            for i in range(start, end):
                print(f"{i + 1:4d}: {lines[i]}")


if __name__ == "__main__":
    main()
