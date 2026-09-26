#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv-sheets/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo 'Missing .venv-sheets; install the existing Sheets environment first.' >&2
  exit 1
fi
if [[ "$(uname -s)" == Darwin ]] && [[ "$(/usr/sbin/sysctl -n hw.optional.arm64 2>/dev/null || true)" == 1 ]]; then
  exec /usr/bin/arch -arm64 "$PYTHON" -B "$ROOT/_src/import_gmail_orders.py" "$@"
fi
exec "$PYTHON" -B "$ROOT/_src/import_gmail_orders.py" "$@"
