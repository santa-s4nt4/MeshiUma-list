#!/usr/bin/env bash
set -euo pipefail

# Always run from the project root, even when invoked from another directory.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

CSV_PATH="${1:-メシウマ.csv}"
if [[ $# -gt 0 ]]; then
  shift
fi

if [[ ! -f "$CSV_PATH" ]]; then
  echo "ERROR: CSVが見つかりません: $CSV_PATH" >&2
  echo "Usage: ./update_data.sh [CSV_PATH] [incremental_update.py options...]" >&2
  exit 1
fi

echo "差分更新を開始します: $CSV_PATH"
python3 scripts/incremental_update.py "$CSV_PATH" "$@"
