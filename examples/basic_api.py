"""Basic Kinglet API example (backward-compatible entry point).

The demo now lives in :mod:`demo-basic.basic_app` as the canonical GA ASGI
demo; this module re-exports it so existing imports keep working.
"""

import runpy
from pathlib import Path

_APP = Path(__file__).resolve().parent / "demo-basic" / "basic_app.py"

if __name__ == "__main__":
    runpy.run_path(str(_APP), run_name="__main__")
else:
    globals().update(
        {k: v for k, v in runpy.run_path(str(_APP)).items() if not k.startswith("__")}
    )
