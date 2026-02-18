#!/usr/bin/env python3
"""
translate_rss.py
- Reads OPML or YAML feed list
- Fetches RSS entries
- Best-effort fetch+extract article text
- Translates to target language
- Writes translated RSS XML per source feed

Usage:
  python scripts/translate_rss.py --opml path/to/input.opml --out_dir output/feeds
"""
from __future__ import annotations
import argparse, hashlib, os, re, sqlite3, sys, time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple, Dict
import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from dotenv import load_dotenv

# OpenAI translator (default)
from openai import OpenAI

UA = "rss-translate/1.0 (+Feedly OPML pipeline)"

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except Exception:
        return default

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except Exception:
        return default

def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "feed"

def load_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS translated_cache(
        key TEXT PRIMARY KEY,
        created_at TEXT,
        translator TEXT,
        target_lang TEXT,
        source_len INTEGER,
        translated TEXT
      )
    """)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS seen_items(
        item_id TEXT PRIMARY KEY,
        first_seen TEXT
      )
    """)
    conn.commit()
    return conn

def cache_get(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT translated FROM translated_cache WHERE key=?", (key,)).fetchone()
    return row[0] if row else None

def cache_put(conn: sqlite3.Connection, key: str, translator: str, target_lang: str, source_text: str, translated: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO translated_cache(key, created_at, translator, target_lang, source_len, translated) VALUES(?,?,?,?,?,?)",
        (key, datetime.utcnow().isoformat(), translator, target_lang, len(source_text), translated)
    )
    conn.commit()

def mark_seen(conn: sqlite3.Connection, item_id: str) -> None:
    conn.execute("INSERT OR IGNORE INTO seen_items(item_id, first_seen) VALUES(?,?)", (item_id, datetime.utcnow().isoformat()))
    conn.commit()

def is_seen(conn: sqlite3.Connection, item_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM seen_items WHERE item_id=?", (item_id,)).fetchone()
    return bool(row)

def parse_opml(opml_path: str) -> List[Tuple[str, str]]:
    import xml.etree.ElementTree as ET
    tree = ET.parse(opml_path)
    root = tree.getroot()
    feeds: List[Tuple[str, str]] = []
    for el in root.iter():
        if el.tag.lower().endswith("outline"):
            xmlurl = el.attrib.get("xmlUrl") or el.attrib.get("xmlurl")
            text = el.attrib.get("text") or el.attrib.get("title") or "Feed"
            if xmlurl:
                feeds.append((text, xmlurl))
    # Deduplicate by URL preserving first title
    seen = set()
    out = []
    for t,u in feeds:
        if u not in seen:
            out.append((t,u))
            seen.add(u)
    return out

def fetch_url(url: str, timeout: int) -> Optional[str]:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
        if r.status_code >= 400:
            return None
        r.encoding = r.apparent_encoding or r.encoding
        return r.text
    except Exception:
        return None

def extract_main_text(html: str) -> str:
    """
    Best-effort text extraction (no heavy dependencies).
    - Removes scripts/styles
    - Prefers <article> text; falls back to <main>; then body
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    cand = soup.find("article") or soup.find("main") or soup.body
    if not cand:
        return ""
    text = cand.get_text("\n", strip=True)
    # Reduce boilerplate
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text

def truncate_for_translation(text: str, max_chars: int = 12000) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    # keep beginning + end (often contains key facts)
    head = text[: int(max_chars * 0.7)]
    tail = text[-int(max_chars * 0.3):]
    return head + "\n\n[...TRUNCATED...]\n\n" + tail

class Translator:
    def translate(self, text: str, target_lang: str) -> str:
        raise NotImplementedError

class OpenAITranslator(Translator):
    def __init__(self, model: str, api_key: str | None):
        api_key = (api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
        if not api_key:
            raise SystemExit(
                "Missing OPENAI_API_KEY. Set it in .env, or pass --api_key to translate_rss.py"
            )
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def translate(self, text: str, target_lang: str) -> str:
        # Keep output strictly in target language.
        system = (
            "You are a precise translation engine. "
            "Translate the user's text faithfully into the target language, preserving names, numbers, and proper nouns. "
            "Do not add commentary. Output ONLY the translation."
        )
        prompt = f"Target language: {target_lang}\n\nText:\n{text}"
        resp = self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        # SDK returns a rich object; output_text is the easiest accessor
        out = getattr(resp, "output_text", None)
        if out:
            return out.strip()
        # fallback: try to find any text content
        try:
            parts = []
            for item in resp.output:
                for c in getattr(item, "content", []) or []:
                    if getattr(c, "type", "") == "output_text":
                        parts.append(getattr(c, "text", ""))
            return "\n".join(parts).strip()
        except Exception:
            return ""

def pick_translator(api_key_override: str | None) -> Tuple[str, Translator]:
    which = (os.environ.get("TRANSLATOR") or "openai").strip().lower()
    if which == "openai":
        model = os.environ.get("OPENAI_MODEL") or "gpt-4.1-mini"
        return which, OpenAITranslator(model=model, api_key=api_key_override)
    raise SystemExit(f"Unsupported TRANSLATOR={which}. This pack includes OpenAI by default.")

def build_rss(feed_title: str, items: List[Dict[str, str]]) -> str:
    # Simple RSS 2.0 writer
    def esc(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    now = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
    out = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>')
    out.append('<rss version="2.0">')
    out.append("<channel>")
    out.append(f"<title>{esc(feed_title)}</title>")
    out.append(f"<link></link>")
    out.append(f"<description>{esc(feed_title)}</description>")
    out.append(f"<lastBuildDate>{now}</lastBuildDate>")
    for it in items:
        out.append("<item>")
        out.append(f"<title>{esc(it.get('title',''))}</title>")
        out.append(f"<link>{esc(it.get('link',''))}</link>")
        out.append(f"<guid isPermaLink=\"false\">{esc(it.get('guid',''))}</guid>")
        if it.get("pubDate"):
            out.append(f"<pubDate>{esc(it['pubDate'])}</pubDate>")
        # Put translated text in description; keep it readable
        desc = it.get("description","")
        out.append(f"<description><![CDATA[{desc}]]></description>")
        out.append("</item>")
    out.append("</channel></rss>")
    return "\n".join(out)

def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--opml", required=True, help="Input OPML containing feeds")
    ap.add_argument("--out_dir", required=True, help="Output directory for translated RSS XML files")
    ap.add_argument("--db", default="output/cache.sqlite", help="SQLite cache path")
    ap.add_argument("--only_lang_ceid", default="", help="Optional: filter Google News feeds by ceid suffix (e.g. ':ru' ':fa' ':zh-Hans' ':ar')")
    ap.add_argument("--api_key", default="", help="OpenAI API key (optional; overrides OPENAI_API_KEY env var)")
    args = ap.parse_args()

    target_lang = (os.environ.get("TRANSLATE_TARGET_LANG") or "en").strip().lower()
    timeout = _env_int("HTTP_TIMEOUT", 20)
    max_items = _env_int("MAX_ITEMS_PER_FEED", 30)

    os.makedirs(args.out_dir, exist_ok=True)
    os.makedirs(os.path.dirname(args.db) or ".", exist_ok=True)

    conn = load_db(args.db)
    translator_name, translator = pick_translator(args.api_key or None)

    feeds = parse_opml(args.opml)
    if args.only_lang_ceid:
        feeds = [(t,u) for (t,u) in feeds if args.only_lang_ceid in u]

    for (title, url) in feeds:
        print(f"\n==> {title} :: {url}")
        parsed = feedparser.parse(url)
        entries = parsed.entries[:max_items]
        out_items = []
        for e in entries:
            link = getattr(e, "link", "") or ""
            eid = sha1((getattr(e, "id", "") or "") + link + (getattr(e, "title", "") or ""))
            if is_seen(conn, eid):
                continue

            raw_title = getattr(e, "title", "") or ""
            raw_summary = getattr(e, "summary", "") or getattr(e, "description", "") or ""
            pub = ""
            try:
                dt = None
                if getattr(e, "published", None):
                    dt = dateparser.parse(e.published)
                elif getattr(e, "updated", None):
                    dt = dateparser.parse(e.updated)
                if dt:
                    pub = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
            except Exception:
                pub = ""

            # Fetch article text best-effort
            article_text = ""
            if link:
                html = fetch_url(link, timeout=timeout)
                if html:
                    article_text = extract_main_text(html)

            # Choose source text to translate
            source_text = article_text.strip() if len(article_text.strip()) >= 400 else BeautifulSoup(raw_summary, "lxml").get_text(" ", strip=True)

            source_text = truncate_for_translation(source_text, max_chars=12000)
            cache_key = sha1(f"{translator_name}:{target_lang}:{source_text}")

            translated = cache_get(conn, cache_key)
            if not translated:
                translated = translator.translate(source_text, target_lang=target_lang)
                if not translated:
                    translated = source_text  # last resort
                cache_put(conn, cache_key, translator_name, target_lang, source_text, translated)

            # Build description: include both (short)
            # Put translation first; keep a short original snippet for audit
            orig_snip = (source_text[:600] + "...") if len(source_text) > 600 else source_text
            desc = "<p><b>Translated:</b></p><p>" + translated.replace("\n", "<br/>") + "</p>"
            desc += "<hr/><p><b>Original snippet:</b></p><p>" + orig_snip.replace("\n", "<br/>") + "</p>"

            out_items.append({
                "title": f"[{target_lang.upper()}] {raw_title}",
                "link": link,
                "guid": eid,
                "pubDate": pub,
                "description": desc
            })
            mark_seen(conn, eid)

        out_title = f"{title} (Translated → {target_lang})"
        rss_xml = build_rss(out_title, out_items)

        fname = slugify(title) + f".{target_lang}.xml"
        out_path = os.path.join(args.out_dir, fname)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(rss_xml)
        print(f"Saved: {out_path}  (items: {len(out_items)})")

if __name__ == "__main__":
    main()
