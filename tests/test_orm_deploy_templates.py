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
