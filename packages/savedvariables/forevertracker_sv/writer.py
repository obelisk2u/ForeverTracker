"""Write Python values the way the WoW client writes SavedVariables files.

For fixtures, tests and the simulator only; the client writes the real files.
"""

from __future__ import annotations

from typing import Any


def _quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _value(v: Any) -> str:
    if v is None:
        return "nil"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return _quote(v)
    if isinstance(v, list):
        lines = ["{"]
        for i, item in enumerate(v, 1):
            lines.append(f"{_value(item)}, -- [{i}]")
        lines.append("}")
        return "\n".join(lines)
    if isinstance(v, dict):
        lines = ["{"]
        for k, item in v.items():
            if item is None:
                continue
            key = f"[{_quote(k)}]" if isinstance(k, str) else f"[{k}]"
            lines.append(f"{key} = {_value(item)},")
        lines.append("}")
        return "\n".join(lines)
    raise TypeError(f"cannot serialise {type(v).__name__}")


def to_savedvariables(globals_: dict[str, Any]) -> str:
    return "\n" + "\n".join(f"{name} = {_value(value)}" for name, value in globals_.items()) + "\n"
