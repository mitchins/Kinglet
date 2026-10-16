import sys
import types

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
    migrate = AsyncMock(return_value={"ok": True})
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
