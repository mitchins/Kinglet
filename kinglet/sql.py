"""
Lightweight SQL helpers for identifier safety in SQLite/D1 contexts.

Notes:
- SQLite/D1 cannot parameterize identifiers (table/column names).
- Callers MUST validate identifiers and parameterize values.
"""

import re

_IDENT_RE = re.compile(r"^[A-Za-z_]\w*$")


def safe_ident(name: str) -> str:
    """Validate a SQL identifier (table/column) and return it.

    Accepts leading ASCII letter or underscore, then word chars.
    Raises ValueError if invalid.
    """
    if not name or not _IDENT_RE.match(name):
        raise ValueError("Invalid SQL identifier")
    return name


def quote_ident_sqlite(name: str) -> str:
    """Return a safely quoted SQLite identifier.

    Caller should first validate via safe_ident if you want to enforce
    a strict naming policy; quoting is provided for completeness.
    """
    return '"' + str(name).replace('"', '""') + '"'
