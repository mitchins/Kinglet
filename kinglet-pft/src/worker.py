"""Minimal benchmark worker for import-path comparison."""

import json
from time import perf_counter
from workers import Response

# Set mode by editing this file for A/B runs:
# - "core": import kinglet
# - "workers": from kinglet import workers
IMPORT_MODE = "core"

start = perf_counter()
if IMPORT_MODE == "workers":
    from kinglet import workers  # noqa: F401
else:
    import kinglet  # noqa: F401

BOOT_MS = (perf_counter() - start) * 1000


async def on_fetch(request, env):
    path = request.url.split("?", 1)[0].rstrip("/")

    if path.endswith("/inspect"):
        from importlib import import_module
        t0 = perf_counter()
        import_module("kinglet")
        import_elapsed = (perf_counter() - t0) * 1000
        return Response(
            json.dumps(
                {
                "mode": IMPORT_MODE,
                "boot_ms": round(BOOT_MS, 3),
                "import_kinglet_ms": round(import_elapsed, 3),
                }
            ),
            headers={"content-type": "application/json"},
        )

    if path.endswith("/inspect_workers"):
        t0 = perf_counter()
        from kinglet import workers  # noqa: F401
        import_elapsed = (perf_counter() - t0) * 1000
        return Response(
            json.dumps(
                {
                "mode": IMPORT_MODE,
                "boot_ms": round(BOOT_MS, 3),
                "import_workers_ms": round(import_elapsed, 3),
                }
            ),
            headers={"content-type": "application/json"},
        )

    return Response(
        json.dumps({"mode": IMPORT_MODE, "boot_ms": round(BOOT_MS, 3)}),
        headers={"content-type": "application/json"},
    )
