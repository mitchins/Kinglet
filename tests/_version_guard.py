# tests/_version_guard.py
import sys

import pytest

if sys.version_info < (3, 12):  # noqa: UP036
    pytest.exit(
        f"\n🚫 Python {sys.version.split()[0]} detected. "
        "This project requires Python 3.12+.\n",
        returncode=1,
    )
