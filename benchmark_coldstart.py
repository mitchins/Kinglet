#!/usr/bin/env python
"""Benchmark script for cold start optimization"""

import subprocess
import sys


def run_isolated_benchmark(script: str, description: str) -> float:
    """Run a benchmark in a fresh Python process"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd="/Users/mitchellcurrie/Projects/Kinglet",
    )
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return 0.0
    return float(result.stdout.strip())


def main():
    print("=" * 60)
    print("KINGLET COLD START BENCHMARK (Isolated Processes)")
    print("=" * 60)
    print()

    # Benchmark 0: Workers-only minimal import (NEW)
    workers_script = """
import time
start = time.perf_counter()
from kinglet.workers import Kinglet, Request, Response, Router, d1_unwrap
print((time.perf_counter() - start) * 1000)
"""
    workers_time = run_isolated_benchmark(workers_script, "Workers-only")
    print(f"Workers minimal (kinglet.workers): {workers_time:.2f}ms")

    # Benchmark 1: Core-only import (new lazy loading)
    core_script = """
import time
start = time.perf_counter()
from kinglet import Kinglet, Request, Response, Router
print((time.perf_counter() - start) * 1000)
"""
    core_time = run_isolated_benchmark(core_script, "Core-only")
    print(f"Core-only import (kinglet): {core_time:.2f}ms")

    # Benchmark 2: Core + common utilities
    utils_script = """
import time
start = time.perf_counter()
from kinglet import Kinglet, Request, Response, Router, d1_unwrap, CacheService
print((time.perf_counter() - start) * 1000)
"""
    utils_time = run_isolated_benchmark(utils_script, "Core+Utils")
    print(f"Core + Utils import: {utils_time:.2f}ms")

    # Benchmark 3: Full import with ORM
    orm_script = """
import time
start = time.perf_counter()
from kinglet import Kinglet, Request, Response, Model, Field, StringField, IntegerField
print((time.perf_counter() - start) * 1000)
"""
    orm_time = run_isolated_benchmark(orm_script, "Core+ORM")
    print(f"Core + ORM import: {orm_time:.2f}ms")

    # Benchmark 4: Full import with testing (simulates test runs)
    test_script = """
import time
start = time.perf_counter()
from kinglet import Kinglet, TestClient, MockD1Database, Model
print((time.perf_counter() - start) * 1000)
"""
    test_time = run_isolated_benchmark(test_script, "Testing")
    print(f"Core + Testing + ORM: {test_time:.2f}ms")

    # Benchmark 5: Everything (old behavior)
    full_script = """
import time
start = time.perf_counter()
from kinglet import (
    Kinglet, Request, Response, Router,
    Model, Field, StringField,
    TestClient, MockD1Database,
    Paginator, PaginationConfig,
    ModelSerializer, serialize_model,
    ValidationSchema, validate_email,
    authz, totp
)
print((time.perf_counter() - start) * 1000)
"""
    full_time = run_isolated_benchmark(full_script, "Full")
    print(f"Full import (all modules): {full_time:.2f}ms")

    print()
    print("=" * 60)
    print("SAVINGS ANALYSIS")
    print("=" * 60)

    if full_time > 0:
        workers_savings = full_time - workers_time
        workers_pct = (workers_savings / full_time) * 100
        core_savings = full_time - core_time
        core_pct = (core_savings / full_time) * 100

        print("kinglet.workers vs full import:")
        print(f"  Savings: {workers_savings:.2f}ms ({workers_pct:.1f}% reduction)")
        print()
        print("kinglet (core-only) vs full import:")
        print(f"  Savings: {core_savings:.2f}ms ({core_pct:.1f}% reduction)")
        print()
        print("RECOMMENDED for Workers: from kinglet.workers import ...")
        print(f"  Fastest possible cold start: {workers_time:.2f}ms")

    print()
    print("=" * 60)
    print("MODULE LOADING ANALYSIS")
    print("=" * 60)

    # Check workers module loading
    workers_module_script = """
import sys
from kinglet import workers
loaded = sorted([k.replace("kinglet.", "") for k in sys.modules if k.startswith("kinglet.")])
print(",".join(loaded))
"""
    result = subprocess.run(
        [sys.executable, "-c", workers_module_script],
        capture_output=True,
        text=True,
        cwd="/Users/mitchellcurrie/Projects/Kinglet",
    )
    workers_loaded = result.stdout.strip().split(",") if result.stdout.strip() else []
    print(f"kinglet.workers loads: {len(workers_loaded)} modules")
    print(f"  {workers_loaded}")

    # Check main module loading
    module_script = """
import sys
import kinglet
loaded = sorted([k.replace("kinglet.", "") for k in sys.modules if k.startswith("kinglet.")])
print(",".join(loaded))
"""
    result = subprocess.run(
        [sys.executable, "-c", module_script],
        capture_output=True,
        text=True,
        cwd="/Users/mitchellcurrie/Projects/Kinglet",
    )
    loaded = result.stdout.strip().split(",") if result.stdout.strip() else []
    print(f"kinglet (main) loads: {len(loaded)} modules")
    print(f"  {loaded}")

    # Check what's deferred
    all_modules = [
        "orm",
        "orm_deploy",
        "orm_errors",
        "orm_migrations",
        "testing",
        "pagination",
        "serializers",
        "validation",
        "openapi",
        "authz",
        "ses",
        "totp",
        "cache_d1",
    ]
    deferred = [m for m in all_modules if m not in loaded]
    print(f"Deferred modules (lazy-loaded): {len(deferred)}")
    print(f"  {deferred}")


if __name__ == "__main__":
    main()
