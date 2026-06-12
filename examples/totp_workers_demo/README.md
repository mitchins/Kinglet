# Kinglet TOTP Workers Demo

Dedicated Cloudflare Workers project for exercising Kinglet auth and TOTP against the real runtime.

This project is pinned to the local Kinglet working copy via an absolute `file:///...` dependency so `pywrangler` exports the code that is actually in this repository.

## Run locally

```bash
rm -rf .venv-workers python_modules vendor
uv lock --refresh
uv sync --group dev --refresh-package kinglet --reinstall-package kinglet
uv run pywrangler sync --force
uv run pywrangler dev
```

## Deploy remotely

```bash
rm -rf .venv-workers python_modules vendor
uv lock --refresh
uv sync --group dev --refresh-package kinglet --reinstall-package kinglet
uv run pywrangler sync --force
uv run pywrangler deploy
```

Before deploying, inspect `python_modules/kinglet` and confirm it contains the local Kinglet source you expect. If it does not, stop there and fix the export state instead of deploying stale modules.

Helper script: run `../../scripts/pywrangler-clean-deploy.sh` from this demo directory to execute the same forced-refresh workflow.

## What this demo proves

- `kinglet` imports without eager `cryptography` loading
- JWT auth works in Workers
- TOTP generation and verification work in Workers
- TOTP secret encryption and decryption work in Workers
- Elevated session checks work in Workers
