"""
Real ASGI server smoke tests: uvicorn and hypercorn (asyncio backend).

Spawns each server as a subprocess running the portable fixture app, then
exercises it over real HTTP. Skipped when the server runtimes are missing.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from tests.asgi_harness import mint_jwt

from .asgi_smoke_app import SMOKE_SECRET

pytestmark = pytest.mark.integration

TARGET = "tests.asgi_smoke_app:application"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_healthy(base_url: str, proc: subprocess.Popen, timeout: float = 30.0):
    """Poll /health until the server answers or the process dies."""
    deadline = time.time() + timeout
    last_error: str | None = None
    while time.time() < deadline:
        if proc.poll() is not None:
            out = (proc.stdout.read() if proc.stdout else "") or ""
            err = (proc.stderr.read() if proc.stderr else "") or ""
            pytest.fail(
                f"server exited early (code {proc.returncode}).\nSTDOUT:\n{out}\nSTDERR:\n{err}"
            )
        try:
            response = httpx.get(f"{base_url}/health", timeout=2.0)
            if response.status_code == 200:
                return
        except Exception as exc:  # noqa: BLE001 - polling until ready
            last_error = str(exc)
        time.sleep(0.2)
    raise TimeoutError(f"server never became healthy: {last_error}")


def _smoke_suite(base_url: str):
    """Compact smoke suite shared by every server backend."""
    client = httpx.Client(base_url=base_url, timeout=10.0)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"ok": True}

    echo = client.post("/echo-json", json={"a": 1})
    assert echo.json() == {"received": {"a": 1}}

    binary = bytes(range(256)) * 256  # 64 KiB
    up = client.post(
        "/echo-bytes",
        content=binary,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert bytes(up.content) == binary
    assert "octet-stream" in up.headers.get("content-type", "")

    cookies = client.get("/cookies")
    assert cookies.headers.get_list("set-cookie") == ["a=1; Path=/", "b=2; Path=/"]

    token = mint_jwt(SMOKE_SECRET, {"sub": "smoke-user", "exp": 2_000_000_000})
    whoami = client.get("/whoami", headers={"authorization": f"Bearer {token}"})
    assert whoami.json() == {"id": "smoke-user"}

    denied = client.get("/whoami")
    assert denied.status_code == 401

    env = client.get("/env-name")
    assert env.json() == {"name": "smoke"}

    boom = client.get("/boom")
    assert boom.status_code == 500
    raw = boom.content
    assert b"secret-sauce" not in raw
    assert json.loads(raw)["error"] == "Internal server error"

    stream = client.get("/stream")
    assert bytes(stream.content) == b"chunk-one-chunk-two-chunk-three"

    # Streaming proof: first chunk arrives well before the producer finishes.
    started = time.time()
    first_at: float | None = None
    chunks: list[bytes] = []
    with client.stream("GET", "/stream-slow") as response:
        assert response.status_code == 200
        for chunk in response.iter_bytes():
            if first_at is None:
                first_at = time.time() - started
            chunks.append(chunk)
    total = time.time() - started
    assert b"".join(chunks) == b"firstsecond"
    assert total >= 1.0, "producer sleep did not elapse; suite timing invalid"
    assert first_at is not None and first_at < total - 0.4, (
        f"no incremental delivery: first chunk at {first_at:.2f}s of {total:.2f}s"
    )

    client.close()


def _stop(proc: subprocess.Popen, timeout: float = 15.0):
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=timeout)


def test_platform_libraries_absent_in_server_environment():
    """The smoke servers run without workers/js/pyodide installed."""
    for module in ("workers", "js", "pyodide"):
        proc = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode != 0, f"{module} unexpectedly importable"


def test_uvicorn_smoke():
    pytest.importorskip("uvicorn")
    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            TARGET,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "info",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=REPO_ROOT,
    )
    try:
        _wait_healthy(f"http://127.0.0.1:{port}", proc)
        _smoke_suite(f"http://127.0.0.1:{port}")
    finally:
        _stop(proc)
    output = proc.stdout.read() if proc.stdout else ""
    assert "Application startup complete" in output
    assert "Application shutdown complete" in output


def test_hypercorn_asyncio_smoke():
    pytest.importorskip("hypercorn")
    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "hypercorn",
            TARGET,
            "--bind",
            f"127.0.0.1:{port}",
            "--worker-class",
            "asyncio",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=REPO_ROOT,
    )
    try:
        _wait_healthy(f"http://127.0.0.1:{port}", proc)
        _smoke_suite(f"http://127.0.0.1:{port}")
    finally:
        _stop(proc)
    output = proc.stdout.read() if proc.stdout else ""
    assert "Running on" in output
