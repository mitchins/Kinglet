#!/usr/bin/env python
"""Upload to PyPI using keyring for credentials.

Usage:
    python upload.py              # Upload to testpypi (default, safer)
    python upload.py pypi         # Upload to production PyPI
    python upload.py --help       # Show help

Setup:
    Store your PyPI tokens in keyring:
        keyring set testpypi __token__
        keyring set pypi __token__
"""

import argparse
import subprocess
import sys
from typing import NoReturn

import keyring


def upload(repository: str = "testpypi") -> NoReturn:
    """Upload dist/* to specified PyPI repository.

    Args:
        repository: PyPI repository name ('testpypi' or 'pypi')

    Raises:
        SystemExit: Always exits with the upload command's return code
    """
    token = keyring.get_password(repository, "__token__")

    if not token:
        print(f"❌ No token found in keyring for '{repository}'")
        print(f"   Run: keyring set {repository} __token__")
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


def main() -> None:
    """Parse arguments and run upload."""
    parser = argparse.ArgumentParser(
        description="Upload package to PyPI using keyring for secure credential handling.",
        epilog="Tokens are stored via: keyring set <repository> __token__",
    )
    parser.add_argument(
        "repository",
        nargs="?",
        default="testpypi",
        choices=["testpypi", "pypi"],
        help="PyPI repository to upload to (default: testpypi)",
    )
    args = parser.parse_args()
    upload(args.repository)


if __name__ == "__main__":
    main()
