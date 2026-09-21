#!/usr/bin/env sh
set -eu
dir=$(dirname "$0")
for candidate in "${UAW_PYTHON:-}" python3 python py; do
  [ -n "$candidate" ] || continue
  if command -v "$candidate" >/dev/null 2>&1; then
    exec "$candidate" "$dir/workflow.py" "$@"
  fi
done
echo "No Python interpreter found; set UAW_PYTHON to one." >&2
exit 127
