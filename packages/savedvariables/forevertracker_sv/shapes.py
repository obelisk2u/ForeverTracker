"""How Lua tables become JSON values before anything is uploaded or validated.

A Lua table can be a list, a map, or (after a manual edit or an addon bug) both at once. JSON, and every
model behind the upload contract, needs one or the other. Every input boundary goes through
:func:`normalize` with these rules:

* a list (keys 1..n, which the parser already turns into a Python ``list``) stays a list;
* a table whose keys are all names stays a map;
* a table whose keys are all positive whole numbers is a list with holes (Lua drops ``nil`` entries):
  it becomes a list in key order;
* anything else is ambiguous and raises :class:`ShapeError` naming where it is: a table mixing list
  positions and names, or with keys that are neither (``true``, ``1.5``, ``0``, ``-1``).

The SavedVariables parser keeps whole-number keys as ``int``. The ``/ft export`` string is JSON, whose
object keys are always strings, so the addon's encoder writes list positions as ``"1"``, ``"3"``...;
``string_indices=True`` reads those as positions so both channels normalize identically.

Nothing here changes the source file: callers reject the record (or the file) and keep the original.
"""

from __future__ import annotations

import re
from typing import Any

from forevertracker_sv.errors import SavedVariablesError

MAX_DEPTH = 64
_POSITION = re.compile(r"^[1-9][0-9]{0,9}$")


class ShapeError(SavedVariablesError):
    """A table whose shape cannot be read without guessing."""

    def __init__(self, path: str, problem: str):
        self.path = path
        self.problem = problem
        super().__init__(f"{path}: {problem}")


def _position(key: Any, string_indices: bool) -> int | None:
    if type(key) is int:
        return key if key >= 1 else None
    if string_indices and isinstance(key, str) and _POSITION.match(key):
        return int(key)
    return None


def normalize(value: Any, path: str = "value", *, string_indices: bool = False, _depth: int = 0) -> Any:
    """Return ``value`` with every table as a JSON list or a string-keyed map (see the module rules)."""
    if _depth > MAX_DEPTH:
        raise ShapeError(path, "tables nested too deeply")
    if isinstance(value, list):
        return [normalize(v, f"{path}[{i}]", string_indices=string_indices, _depth=_depth + 1) for i, v in enumerate(value, 1)]
    if not isinstance(value, dict):
        return value
    if not value:
        return {}
    positions: dict[int, Any] = {}
    names: dict[str, Any] = {}
    for key, item in value.items():
        index = _position(key, string_indices)
        if index is not None:
            positions[index] = item
        elif isinstance(key, str):
            names[key] = item
        else:
            raise ShapeError(path, f"has a key that is neither a name nor a list position ({key!r})")
    if positions and names:
        first_name = sorted(names)[0]
        raise ShapeError(path, f"mixes list positions ({min(positions)}) with named fields ({first_name!r})")
    if positions:
        return [
            normalize(positions[i], f"{path}[{i}]", string_indices=string_indices, _depth=_depth + 1) for i in sorted(positions)
        ]
    return {k: normalize(v, f"{path}.{k}", string_indices=string_indices, _depth=_depth + 1) for k, v in names.items()}
