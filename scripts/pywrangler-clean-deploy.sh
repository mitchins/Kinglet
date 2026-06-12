#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
demo_dir="$(cd "$script_dir/../examples/totp_workers_demo" && pwd)"

cd "$demo_dir"

if [[ ! -f wrangler.toml ]]; then
  echo "wrangler.toml not found in $demo_dir" >&2
  exit 1
fi

rm -rf .venv-workers python_modules vendor
uv lock --refresh
uv sync --group dev --refresh-package kinglet --reinstall-package kinglet
uv run pywrangler sync --force

echo "Checking packaged Kinglet source..."
uv run python - <<'PY'
from pathlib import Path

p = Path("python_modules/kinglet")
assert p.exists(), "python_modules/kinglet missing"
print("Packaged Kinglet files:", len(list(p.rglob("*.py"))))
PY

uv run pywrangler deploy "$@"
