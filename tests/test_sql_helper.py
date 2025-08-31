import pytest

from kinglet.sql import quote_ident_sqlite, safe_ident


def test_safe_ident_accepts_valid_names():
    for name in ["users", "user_1", "_table", "A1", "CamelCase", "snake_case_2"]:
        assert safe_ident(name) == name


@pytest.mark.parametrize(
    "bad",
    [
        "",  # empty
        "1abc",  # starts with digit
        "user-name",  # hyphen not allowed
        "user name",  # space not allowed
        't"able',  # quote in identifier
        "*weird*",
    ],
)
def test_safe_ident_rejects_invalid_names(bad):
    with pytest.raises(ValueError):
        safe_ident(bad)


def test_quote_ident_sqlite_escapes_quotes():
    assert quote_ident_sqlite('foo"bar') == '"foo""bar"'
