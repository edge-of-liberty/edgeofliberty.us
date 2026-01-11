#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$ROOT/_data"
INCLUDES="$ROOT/_includes"
VENDORS_SRC="$ROOT/_vendors"
IMAGES="$ROOT/_images"
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
