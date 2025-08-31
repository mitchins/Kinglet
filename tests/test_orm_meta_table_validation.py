import pytest

from kinglet.orm import Model, StringField


def test_modelmeta_rejects_invalid_table_name():
    with pytest.raises(ValueError):

        class BadTable(Model):
            name = StringField()

            class Meta:
                table_name = "bad-table"  # invalid hyphen
