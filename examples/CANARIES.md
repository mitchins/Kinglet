# Live canary matrix

Four disposable Workers stay deployed as regression probes against the real
Cloudflare runtime. They use the personal account, dedicated scratch
resources, and dummy secrets — no customer data, no production bindings.
Each demo directory holds its own `smoke.py` (`uv run python smoke.py`,
non-zero exit on failure).

Redeploying is safe at any time (each deploy is a fresh immutable version);
deleting is safe too (nothing else depends on these workers or resources).

| Worker | Entry | Bound resources | Smoke | Proves |
|---|---|---|---|---|
| `kinglet-demo-basic` | GA ASGI (`asgi.entrypoint(app.asgi)`) | vars only (`API_TOKEN`, `ENVIRONMENT`) | `examples/demo-basic/smoke.py` | Portable baseline: routing, `/api` prefix, JSON, validation, custom security decorator, OpenAPI |
| `kinglet-demo-orm` | GA ASGI | D1 `kinglet-demo-orm`, vars (`MIGRATION_TOKEN`) | `examples/orm_integration_test/smoke.py` | `scope["env"] → request.env.DB → ORM`: migrate, CRUD, nullable fields, constraint errors, filtering, 404s |
| `kinglet-demo-r2` | GA ASGI | R2 `kinglet-demo-r2` | `examples/demo-r2/smoke.py` | Binary integrity: upload/download exact SHA-256, MIME preserved, no base64/string expansion |
| `kinglet-demo-totp` | Legacy `WorkerEntrypoint` + `await app(request, self.env)` (deliberately unconverted) | vars only (dummy JWT/TOTP secrets) | `examples/totp_workers_demo/smoke.py` | Backward compatibility: existing deployments unaffected; JWT auth, TOTP setup/verify, Web Crypto roundtrip, elevated sessions |

- Compatibility date: `2026-09-21` on all four (current at deployment; bump together when reprobing a runtime change).
- Kinglet source: git `main` at deploy time (vendored into `python_modules/`; hashes verified pre-deploy).
- Tooling notes (learned deploying these): the `pywrangler` CLI with `--allow-build` ships inside `workers-py>=1.17` (use `uv run pywrangler`, Node 24 — Node 26 breaks `pywrangler sync`); git deps require `--allow-build`; deploy-only demo projects need `[tool.setuptools] py-modules = []` to build.
