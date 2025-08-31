from kinglet.orm import IntegerField, Model, QuerySet, StringField


class Dummy(Model):
    name = StringField()
    age = IntegerField()

    class Meta:
        table_name = "dummies"


class _DB:
    pass


def _qs():
    return QuerySet(Dummy, _DB())


def test_where_clause_in_and_like_variants():
    qs = _qs()
    qs._where_conditions = [
        ("name LIKE ? -- startswith", "abc"),
        ("name LIKE ? -- endswith", "xyz"),
        ("name LIKE ? -- contains", "mid"),
        ("LOWER(name) LIKE LOWER(?) -- icontains", "MiX"),
        ("age IN (?, ?, ?)", [1, 2, 3]),
    ]

    where, params = qs._build_where_clause()
    assert " AND " in where
    # startswith adds trailing %
    assert params[0].endswith("%")
    # endswith adds leading %
    assert params[1].startswith("%")
    # contains wraps both sides
    assert params[2].startswith("%") and params[2].endswith("%")
    # icontains wraps both sides
    assert params[3].startswith("%") and params[3].endswith("%")
    # IN expands all
    assert params[4:] == [1, 2, 3]
