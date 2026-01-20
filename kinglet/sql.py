"""
Lightweight SQL helpers for identifier safety in SQLite/D1 contexts.

Notes:
- SQLite/D1 cannot parameterize identifiers (table/column names).
- Callers MUST validate identifiers and parameterize values.

Cold Start Optimization: Regex is lazy-compiled on first use.
"""

import re
from re import Pattern

# Lazy-compiled regex for SQL identifier validation
_IDENT_RE: Pattern | None = None


def _get_ident_regex() -> Pattern:
    """Get the SQL identifier regex, compiling lazily on first use."""
    global _IDENT_RE
    if _IDENT_RE is None:
        _IDENT_RE = re.compile(r"^[A-Za-z_]\w*$")
    return _IDENT_RE


def safe_ident(name: str) -> str:
    """Validate a SQL identifier (table/column) and return it.

    Accepts leading ASCII letter or underscore, then word chars.
    Raises ValueError if invalid.
    """
    if not name or not _get_ident_regex().match(name):
        raise ValueError("Invalid SQL identifier")
    return name


def quote_ident_sqlite(name: str) -> str:
    """Return a safely quoted SQLite identifier.

    Caller should first validate via safe_ident if you want to enforce
    a strict naming policy; quoting is provided for completeness.
    """
    return '"' + str(name).replace('"', '""') + '"'
