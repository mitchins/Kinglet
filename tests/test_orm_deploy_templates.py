import sys
import types

import pytest

from kinglet.orm_deploy import generate_migration_endpoint, generate_status_endpoint


def _install_temp_models_module(mod_name: str):
    mod = types.ModuleType(mod_name)
    sys.modules[mod_name] = mod
    # Create a simple Model subclass inside the module
    from kinglet.orm import Model, StringField

    class TempModel(Model):
        name = StringField()

        class Meta:
            table_name = "temp_models"

    mod.TempModel = TempModel
    return mod


def test_generate_migration_endpoint_substitutions():
    mod_name = "tmp_models_mod"
    _install_temp_models_module(mod_name)

    code = generate_migration_endpoint(mod_name)
    assert mod_name in code
    # Should include class name from the module
    assert "TempModel" in code


def test_generate_status_endpoint_substitutions():
    mod_name = "tmp_models_mod2"
    _install_temp_models_module(mod_name)

    code = generate_status_endpoint(mod_name)
    assert mod_name in code


async def test_generated_migration_handler_returns_dictionary(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from kinglet import Kinglet, SchemaManager

    _install_temp_models_module("generated_models")
    migrate = AsyncMock(return_value={"TempModel": True})
    monkeypatch.setattr(SchemaManager, "migrate_all", migrate)
    namespace = {"app": Kinglet()}
    exec(generate_migration_endpoint("generated_models"), namespace)
    request = SimpleNamespace(
        header=lambda *args: "secret",
        env=type("Env", (dict,), {"DB": object()})(MIGRATION_TOKEN="secret"),
    )
    result = await namespace["migrate_database"](request)
    assert result["status"] == "success"
    migrate.assert_awaited_once()


async def test_generated_status_reads_bundled_schema_lock(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from kinglet import Kinglet
    from kinglet.orm_migrations import MigrationTracker

    _install_temp_models_module("generated_status_models")
    monkeypatch.chdir(tmp_path)
    from kinglet.constants import SCHEMA_LOCK_FILE

    (tmp_path / SCHEMA_LOCK_FILE).write_text('{"migrations": [{"version": "v1"}]}')
    monkeypatch.setattr(
        MigrationTracker,
        "get_migration_status",
        AsyncMock(
            return_value={
                "current_version": "v1",
                "migrations_count": 1,
                "healthy": True,
                "migrations": [],
            }
        ),
    )
    namespace = {"app": Kinglet()}
    exec(generate_status_endpoint("generated_status_models"), namespace)
    result = await namespace["migration_status"](
        SimpleNamespace(env=SimpleNamespace(DB=object()))
    )
    assert result["expected_version"] == "v1"
    assert result["up_to_date"] is True


@pytest.mark.parametrize(
    "generator", [generate_migration_endpoint, generate_status_endpoint]
)
@pytest.mark.parametrize("token", [None, "incorrect"])
async def test_generated_migration_denial_is_401_over_asgi(generator, token):
    import json

    from kinglet import Kinglet

    from .asgi_harness import Harness, http_scope, response_body, response_start

    _install_temp_models_module("generated_denied_models")
    app = Kinglet()
    exec(generator("generated_denied_models"), {"app": app})
    headers = {} if token is None else {"X-Migration-Token": token}
    harness = Harness(
        http_scope(
            "/api/_migrate",
            method="POST",
            headers=headers,
            env={"MIGRATION_TOKEN": "secret"},
        ),
        [],
    )
    await app.asgi(harness.scope, harness.receive, harness.send)
    assert response_start(harness.sent)["status"] == 401
    assert json.loads(response_body(harness.sent)) == {"error": "Unauthorized"}


@pytest.mark.parametrize(
    "generator,method,results",
    [
        (generate_migration_endpoint, "migrate_all", {"TempModel": "Error: failed"}),
        (
            generate_status_endpoint,
            "apply_migrations",
            {"failed": [{"error": "failed"}]},
        ),
    ],
)
async def test_generated_migration_failure_returns_500(
    generator, method, results, monkeypatch
):
    import json
    from unittest.mock import AsyncMock

    from kinglet import Kinglet, SchemaManager
    from kinglet.orm_migrations import MigrationTracker

    from .asgi_harness import Harness, http_scope, response_body, response_start

    _install_temp_models_module("generated_failed_models")
    owner = SchemaManager if method == "migrate_all" else MigrationTracker
    monkeypatch.setattr(owner, method, AsyncMock(return_value=results))
    app = Kinglet()
    exec(generator("generated_failed_models"), {"app": app})
    harness = Harness(
        http_scope(
            "/api/_migrate",
            method="POST",
            headers={"X-Migration-Token": "secret"},
            env={"MIGRATION_TOKEN": "secret", "DB": object()},
        ),
        [],
    )
    await app.asgi(harness.scope, harness.receive, harness.send)
    assert response_start(harness.sent)["status"] == 500
    payload = json.loads(response_body(harness.sent))
    assert payload["status"] == "failed"
    assert payload["migrated" if method == "migrate_all" else "results"] == results
