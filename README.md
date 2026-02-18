# RSS Auto-Translation Pipeline (Feedly-friendly)

This project:
1) Reads one or more OPML files (or a YAML list of feeds)
2) Pulls RSS/Atom feeds (RU/FA/ZH/AR/etc.)
3) Fetches each article (best-effort) and extracts readable text
4) Translates to **English or Spanish** using one of:
   - OpenAI API (recommended)
   - DeepL API (optional)
   - Google Cloud Translate (optional)
5) Writes **translated RSS feeds** as static XML files
6) Generates a new OPML that points Feedly to those translated feed URLs

## Quick start

### 1) Install
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Configure
Copy `.env.example` to `.env` and set at least:
- `OPENAI_API_KEY`
- `TRANSLATE_TARGET_LANG` = `en` or `es`
- `PUBLIC_BASE_URL` = where you'll host the translated XML files (e.g. GitHub Pages URL)

### 3) Run (translate feeds)
```bash
python scripts/translate_rss.py --opml input.opml --out_dir output/feeds
```

### 4) Generate Feedly OPML pointing to translated feeds
```bash
python scripts/build_translated_opml.py --source_opml input.opml --translated_dir output/feeds --out_opml output/opml/translated.opml
```

## Hosting translated feeds (so Feedly can subscribe)

Feedly needs public URLs. Easiest options:
- GitHub Pages (commit `output/feeds/*.xml`)
- Any static web host (S3/CloudFront, Netlify, Vercel static, etc.)

Set `PUBLIC_BASE_URL` to the folder URL that will serve your `*.xml` files.
Example:
`PUBLIC_BASE_URL=https://YOURNAME.github.io/yourrepo/feeds/`

## Notes / limitations
- Some sites block scraping; in that case we fall back to translating the RSS summary/description.
- Deduping uses a lightweight SQLite cache (`output/cache.sqlite`).
- Translation chunks are limited to keep requests safe; long articles are summarized then translated if needed.

## Troubleshooting OPML parse errors
- Inspect lines near an error:
  `python scripts/inspect_opml_lines.py --path config/caribbean_intel.opml --start 10 --end 30`
- Sanitize OPML (creates .bak and writes sanitized output):
  `python scripts/sanitize_opml.py --path config/caribbean_intel.opml --out config/caribbean_intel.sanitized.opml`
