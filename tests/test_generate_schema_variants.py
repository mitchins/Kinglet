import sys
import types

from kinglet.orm_deploy import generate_schema


def _install_models(mod_name: str):
    mod = types.ModuleType(mod_name)
    sys.modules[mod_name] = mod
    from kinglet.orm import DateTimeField, Model, StringField

    class A(Model):
        name = StringField(index=True)  # Explicit index for performance-critical field
        created_at = DateTimeField()  # This will generate an index

        class Meta:
            table_name = "dups"

    class B(Model):
        name = StringField()

        class Meta:
            table_name = "dups"  # duplicate to exercise warning path

    mod.A = A
    mod.B = B
    return mod


def test_generate_schema_cleanslate_and_indexes():
    modname = "gen_schema_mod"
    _install_models(modname)

    sql = generate_schema(modname, include_indexes=True, cleanslate=True)
    # Drop statements from cleanslate
    assert "DROP TABLE IF EXISTS" in sql
    # Create statements
    assert "CREATE TABLE" in sql
    # Indexes
    assert "CREATE INDEX" in sql or "CREATE UNIQUE INDEX" in sql
