#!/usr/bin/env python3
"""
build_translated_opml.py
- Reads a source OPML (original feeds)
- Looks at translated_dir for *.xml outputs
- Writes a new OPML pointing to PUBLIC_BASE_URL + filename
This is what you import into Feedly.

Usage:
  python scripts/build_translated_opml.py --source_opml input.opml --translated_dir output/feeds --out_opml output/opml/translated.opml
"""
from __future__ import annotations
import argparse, os, re, xml.etree.ElementTree as ET
from dotenv import load_dotenv

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "feed"

def parse_opml_titles(opml_path: str):
    tree = ET.parse(opml_path)
    root = tree.getroot()
    titles = []
    for el in root.iter():
        if el.tag.lower().endswith("outline"):
            xmlurl = el.attrib.get("xmlUrl") or el.attrib.get("xmlurl")
            text = el.attrib.get("text") or el.attrib.get("title") or "Feed"
            if xmlurl:
                titles.append(text)
    # dedupe preserving order
    seen=set(); out=[]
    for t in titles:
        if t not in seen:
            out.append(t); seen.add(t)
    return out

def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--source_opml", required=True)
    ap.add_argument("--translated_dir", required=True)
    ap.add_argument("--out_opml", required=True)
    ap.add_argument("--collection_name", default="Translated Feeds")
    ap.add_argument("--base_url", default="", help="Public base URL for hosted feeds (optional; overrides PUBLIC_BASE_URL env var)")
    args = ap.parse_args()

    base_url = (args.base_url or os.environ.get("PUBLIC_BASE_URL") or "").strip()
    if not base_url.endswith("/"):
        raise SystemExit("PUBLIC_BASE_URL must be set and must end with '/' (e.g. https://.../feeds/)")

    titles = parse_opml_titles(args.source_opml)

    # Map expected filenames from titles to actual files
    files = {fn: os.path.join(args.translated_dir, fn) for fn in os.listdir(args.translated_dir) if fn.lower().endswith(".xml")}

    opml = ET.Element("opml", {"version":"2.0"})
    head = ET.SubElement(opml, "head")
    ET.SubElement(head, "title").text = args.collection_name

    body = ET.SubElement(opml, "body")
    root_outline = ET.SubElement(body, "outline", {"text": args.collection_name})

    missing = 0
    for t in titles:
        # We don't know target lang in filename; add all matching patterns
        prefix = slugify(t) + "."
        matched = [fn for fn in files.keys() if fn.startswith(prefix)]
        if not matched:
            missing += 1
            continue
        folder = ET.SubElement(root_outline, "outline", {"text": t})
        for fn in sorted(matched):
            ET.SubElement(folder, "outline", {
                "text": f"{t} ({fn.split('.')[-2].upper()} translated)",
                "type": "rss",
                "xmlUrl": base_url + fn
            })

    os.makedirs(os.path.dirname(args.out_opml) or ".", exist_ok=True)
    ET.ElementTree(opml).write(args.out_opml, encoding="utf-8", xml_declaration=True)
    print(f"Wrote: {args.out_opml}")
    if missing:
        print(f"Note: {missing} source titles had no matching translated XML yet (run translate_rss.py first).")

if __name__ == "__main__":
    main()
