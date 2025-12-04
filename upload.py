#!/usr/bin/env python
"""Upload to PyPI using keyring for credentials."""

import subprocess
import sys

import keyring


def upload(repository: str = "testpypi"):
    """Upload dist/* to specified PyPI repository."""
    token = keyring.get_password(repository, "__token__")

    if not token:
        print(f"❌ No token found in keyring for '{repository}'")
        sys.exit(1)

    cmd = [
        "uv",
        "run",
        "twine",
        "upload",
        "--repository",
        repository,
        "--skip-existing",
        "-u",
        "__token__",
        "-p",
        token,
        "dist/*",
    ]

    print(f"📦 Uploading to {repository}...")
    result = subprocess.run(cmd, shell=False)
    sys.exit(result.returncode)


if __name__ == "__main__":
    repo = sys.argv[1] if len(sys.argv) > 1 else "testpypi"
    upload(repo)
