"""Character name handling for Forever's two-part names.

Forever names are "First Surname" and unique per region. The second value returned by
``UnitName``-family APIs is a surname, never a realm (docs/RESEARCH_FOREVER_API.md section 4.1).
"""

from __future__ import annotations

import re
import unicodedata

_SPACES = re.compile(r"\s+")


def full_name(name: str, surname: str | None) -> str:
    name = _SPACES.sub(" ", name.strip())
    if surname and surname.strip():
        return f"{name} {_SPACES.sub(' ', surname.strip())}"
    return name


def normalize_name(value: str) -> str:
    """Case- and width-insensitive form used for lookup and search (accents are kept)."""
    return _SPACES.sub(" ", unicodedata.normalize("NFKC", value).casefold().strip())


def normalize_full_name(name: str, surname: str | None) -> str:
    return normalize_name(full_name(name, surname))


def search_pattern(query: str) -> str:
    """Escape LIKE metacharacters in a user-supplied search term."""
    q = normalize_name(query)
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
