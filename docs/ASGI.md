# Kinglet ASGI boundary

Supported scope: **ASGI 3 HTTP and lifespan on asyncio servers**
(verified against uvicorn and hypercorn with the asyncio worker).
WebSocket scopes and other scope types are rejected explicitly.

## Entry points

The same portable application — routes, middleware, authorization,
validation, request handling and responses — is served through one shared
dispatch core (`Kinglet._dispatch`):

```text
Cloudflare workers.asgi ──┐
                         ├── app.asgi ───────┐
Ordinary ASGI server ─────┘                  │
                                            ├── shared dispatch
Existing app(request, env) ── legacy adapter ┘
```

```python
# application.py
from kinglet import Kinglet

app = Kinglet()

@app.get("/health", public=True)
async def health(request):
    return {"ok": True}

application = app.asgi
```

```python
# worker.py (Cloudflare GA Python Workers entry point)
from workers import asgi
from application import application

Default = asgi.entrypoint(application)
```

```bash
# ordinary server
uv run uvicorn application:application
```

`Kinglet.__call__` (`await app(request, env)`) is preserved unchanged for
backward compatibility. There is no signature guessing: the two interfaces
are explicit and converge on `_dispatch`.

## Environment

- On Cloudflare, bindings come from `scope["env"]` (supplied by the SDK).
  There is no `scope["ctx"]` dependency.
- Outside Workers, inject settings explicitly with `kinglet.asgi.with_env`:

```python
from kinglet.asgi import with_env

application = with_env(app.asgi, {"JWT_SECRET": "...", "DB": db})
```

- `request.env.NAME` ergonomics and mapping support are unchanged, and
  binding object identity is preserved (no copy/serialization).
- A request's environment is never stored on the application global, and no
  secrets are discovered from process environment variables.
- A public portable route works with no bindings; missing required bindings
  fail explicitly (attribute access raises, surfaced as a 500, not a skip).

## Request state

Each request gets a fresh `request.state` namespace. Lifespan
`scope["state"]`, when present, seeds it with a shallow copy: referenced
application resources may be shared, but the namespace itself is
request-local.

## Lifespan

`lifespan.startup` / `lifespan.shutdown` receive an inexpensive
acknowledgement only. Kinglet has no lifecycle callbacks, so nothing runs at
startup: no migrations, schema inspection, cache warming or remote reads.
Notably, the Cloudflare SDK currently runs a lifespan cycle **per HTTP
request**, so startup must never be treated as once-per-isolate, shutdown
never as a guaranteed eviction callback, and no global "already started"
flag is kept. HTTP works whether or not the host initiates lifespan.

## Responses on the ASGI path

Portable results (`None`, `str`, `bytes`, JSON `dict`/`list`, async
iterables and lazy sync iterables of `str`/`bytes` for streaming) are
emitted with status codes and repeated headers (separate `Set-Cookie`
values) preserved. Everything else raises `TypeError`: no `str(obj)`,
base64, or empty-success fallbacks. After transmission starts, failures
propagate after stream cleanup — no second error response is attempted.

Workers-native responses are **unsupported on the ASGI path** (they raise
`TypeError`) and remain supported on the legacy `await app(request, env)`
path, which passes them through untouched.

## Binary bodies

Request bodies are read fully until `more_body` is false with bytes
preserved exactly; one cached body backs repeated `bytes()`/`text()`/
`json()` reads. `body()` stays a text alias, and empty/malformed JSON still
parses to `None`; transport failures raise instead.

## Prefixes

Kinglet's configured route prefix (`Kinglet(root_path=...)`, baked into
routes at registration) and ASGI's `scope["root_path"]` (mount supplied by
the host, stripped on segment boundaries before routing) are independent:

| Kinglet prefix | ASGI mount | Incoming path   | Route |
| -------------- | ---------- | --------------- | ----- |
| Empty          | Empty      | `/items`        | `/items` |
| `/api`         | Empty      | `/api/items`    | `/items` |
| Empty          | `/api`     | `/api/items`    | `/items` |
| `/v1`          | `/api`     | `/api/v1/items` | `/items` |

`request.path` is the router-relative path; `request.full_path` is the
externally visible path.
