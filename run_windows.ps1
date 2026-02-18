Param(
  [string]$OpmlPath = "config\caribbean_intel.opml",
  [string]$OutDir   = "output\feeds",
  [string]$TargetLang = "en"
)

$ErrorActionPreference = "Stop"

# Load .env if present
if (Test-Path ".\.env") {
  Get-Content ".\.env" | ForEach-Object {
    if ($_ -match "^\s*#") { return }
    if ($_ -match "^\s*$") { return }
    $parts = $_ -split "=", 2
    if ($parts.Count -eq 2) {
      $name = $parts[0].Trim()
      $val  = $parts[1].Trim()
      if ($name -and $val) { [Environment]::SetEnvironmentVariable($name, $val, "Process") }
    }
  }
}

# Ensure venv
if (!(Test-Path ".\.venv")) { python -m venv .venv }

# Install deps
.\.venv\Scripts\python -m pip install -r requirements.txt

# Ensure key exists (prompt if not)
if (-not $env:OPENAI_API_KEY -or $env:OPENAI_API_KEY.Trim().Length -lt 10) {
  $env:OPENAI_API_KEY = Read-Host "Enter OPENAI_API_KEY"
}

$env:TRANSLATE_TARGET_LANG = $TargetLang

# Translate feeds
.\.venv\Scripts\python scripts\translate_rss.py --opml $OpmlPath --out_dir $OutDir

# Build OPML only if base URL exists (prompt)
if (-not $env:PUBLIC_BASE_URL -or -not $env:PUBLIC_BASE_URL.EndsWith("/")) {
  $env:PUBLIC_BASE_URL = Read-Host "Enter PUBLIC_BASE_URL (must end with /) e.g. https://YOURNAME.github.io/YOURREPO/feeds/"
}

.\.venv\Scripts\python scripts\build_translated_opml.py `
  --source_opml $OpmlPath `
  --translated_dir $OutDir `
  --out_opml output\opml\translated.opml `
  --collection_name "Caribbean Intel (Translated)"

# Generate daily static site
Write-Host "
=== Generating Daily Site ===" -ForegroundColor Cyan
python scripts/generate_daily_site.py
