#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/nancy/edgeofliberty.us"
DATA_DIR="$ROOT/_data"
INCLUDES="$ROOT/_includes"
VENDORS_SRC="$ROOT/vendors"
IMAGES="$ROOT/images"
SRC="$ROOT/_src"

YEAR=2026
CSV_FILE="$DATA_DIR/2026 Edge of Liberty Craft Fairs - Craft Fair Planning.csv"
BUILD_JSON="$DATA_DIR/build.json"

###############################################################################
# Helpers
###############################################################################

require_file() {
  if [[ ! -f "$1" ]]; then
    echo "[FATAL] Missing required file: $1" >&2
    exit 1
  fi
}

###############################################################################
# Build sitemap.xml (pure bash)
###############################################################################

build_sitemap() {
  echo "[INFO] Generating sitemap.xml..."

  BASE_URL="https://www.edgeofliberty.us"
  OUT="$ROOT/sitemap.xml"

  {
    echo '<?xml version="1.0" encoding="UTF-8"?>'
    echo '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    echo "  <url><loc>${BASE_URL}/</loc></url>"

    find "$ROOT" -maxdepth 2 -type f -name "*.html" ! -name "index.html" | while read -r file; do
      fname="$(basename "$file")"
      echo "  <url><loc>${BASE_URL}/${fname}</loc></url>"
    done

    echo '</urlset>'
  } > "$OUT"

  if [[ ! -s "$OUT" ]]; then
    echo "[FATAL] sitemap.xml was not generated correctly" >&2
    exit 1
  fi

  echo "[OK] sitemap.xml generated at $OUT"
}

###############################################################################
# CSV → JSON
###############################################################################

parse_csv() {
  echo "[INFO] Parsing CSV..."
  require_file "$SRC/parse_csv.py"
  require_file "$CSV_FILE"

  python3 "$SRC/parse_csv.py" "$CSV_FILE" "$YEAR" > "$BUILD_JSON"

  if [[ ! -s "$BUILD_JSON" ]]; then
    echo "[FATAL] build.json is empty or missing" >&2
    exit 1
  fi

  echo "[OK] build.json generated ($(wc -c < "$BUILD_JSON") bytes)"
}

###############################################################################
# Scaffold vendor dirs
###############################################################################

scaffold_vendors() {
  echo "[INFO] Scaffolding vendor include directories..."
  require_file "$SRC/scaffold_vendors.py"
  parse_csv
  python3 "$SRC/scaffold_vendors.py" "$ROOT" "$BUILD_JSON"
}

###############################################################################
# Build vendor pages
###############################################################################

build_vendors() {
  echo "[INFO] Generating vendor pages..."
  require_file "$SRC/build_vendors.py"
  parse_csv
  python3 "$SRC/build_vendors.py" "$ROOT" "$BUILD_JSON"
}

###############################################################################
# Build date pages
###############################################################################

build_dates() {
  echo "[INFO] Generating date pages..."
  require_file "$SRC/build_dates.py"
  parse_csv
  python3 "$SRC/build_dates.py" "$ROOT" "$BUILD_JSON"
}

###############################################################################
# Build home page
###############################################################################

build_home() {
  echo "[INFO] Generating home page..."
  require_file "$SRC/build_home.py"
  parse_csv
  python3 "$SRC/build_home.py" "$ROOT" "$BUILD_JSON"
}

###############################################################################
# Dispatcher
###############################################################################

case "${1:-}" in
  scaffold)
    scaffold_vendors
    ;;
  vendors)
    build_vendors
    ;;
  dates)
    build_dates
    ;;
  home)
    build_home
    ;;
  all)
    echo "[INFO] Starting full site build..."
    scaffold_vendors
    build_vendors
    build_dates
    build_home
    build_sitemap

    echo "[INFO] Staging all changes..."
    git add .

    if ! git diff --cached --quiet; then
      msg="Site build $(date '+%Y-%m-%d %H:%M:%S')"
      git commit -m "$msg"
      echo "[OK] Committed: $msg"

      echo "[INFO] Pushing to origin..."
      if git push; then
        echo "[OK] Push successful."
      else
        echo "[WARN] Push failed. Resolve manually." >&2
      fi
    else
      echo "[INFO] No changes to commit."
    fi

    echo "[INFO] Build complete."
    ;;
  *)
    echo "Usage: ./build.sh [all|vendors|dates|home|scaffold]"
    ;;
esac
