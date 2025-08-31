# Kinglet + Cloudflare Workers Demo

```python
from kinglet import Kinglet

app = Kinglet()

@app.get("/")
async def hello(request):
    return {"message": "Hello from Kinglet!"}

async def on_fetch(request, env):
    return await app(request, env)
```

## Quick Start

```bash
uv add pywrangler kinglet
uv run pywrangler dev
uv run pywrangler deploy
```

## Key Differences from Cloudflare's FastAPI Example

This demo fixes issues in the [official FastAPI example](https://github.com/cloudflare/python-workers-examples/tree/main/03-fastapi):

- ✅ Use `uv pywrangler` (not `npx wrangler`)
- ✅ Use `pyproject.toml` (not `cf-requirements.txt`)
- ✅ Clean `python_modules/` to avoid bloated deployments
- ✅ Current compatibility date

## Files

**pyproject.toml**
```toml
[project]
name = "kinglet-worker"
dependencies = ["kinglet"]
requires-python = ">=3.12"
```

**wrangler.toml**
```toml
name = "kinglet-demo"
main = "src/worker.py"
compatibility_flags = ["python_workers"]
compatibility_date = "2023-12-18"
```

**src/worker.py** - See the example above

## Testing

```python
from kinglet import TestClient
client = TestClient(app)
status, headers, body = client.request("GET", "/")
# Works without HTTP server
```

---

*Updated from Cloudflare's FastAPI example with current tooling and Kinglet.*
