"""A strict, data-only parser for WoW SavedVariables files.

Accepted grammar (the subset the WoW client writes):

    file       := { NAME '=' value }
    value      := 'nil' | 'true' | 'false' | NUMBER | STRING | table
    table      := '{' [ field { (',' | ';') field } [',' | ';'] ] '}'
    field      := '[' value ']' '=' value | NAME '=' value | value

Comments (`-- ...` and `--[[ ... ]]`) are skipped. Anything else (function calls, operators,
concatenation, variables on the right-hand side) is rejected. Nothing is ever executed.

Lua tables become Python values:
  * a table whose keys are exactly 1..n becomes a ``list`` (an empty table becomes ``[]``),
  * any other table becomes a ``dict`` whose keys are ``str``, ``int``, ``float`` or ``bool``,
  * ``nil`` entries are dropped, as in Lua.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from forevertracker_sv.errors import SavedVariablesError


@dataclass(frozen=True)
class ParseLimits:
    max_bytes: int = 32 * 1024 * 1024
    max_depth: int = 48
    max_string_bytes: int = 64 * 1024
    max_values: int = 5_000_000
    max_abs_integer: int = 2**63


_TOKEN_RE = re.compile(
    r"""
    (?P<ws>[ \t\r\n\f\v]+)
  | (?P<block_comment>--\[(?P<eq>=*)\[.*?\](?P=eq)\])
  | (?P<line_comment>--[^\n]*)
  | (?P<string>"(?:[^"\\\n]|\\(?:\r\n|.|\n))*"|'(?:[^'\\\n]|\\(?:\r\n|.|\n))*')
  | (?P<number>-?(?:0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?))
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<punct>[{}\[\]=,;])
    """,
    re.VERBOSE | re.DOTALL,
)

_SIMPLE_ESCAPES = {
    "a": 7, "b": 8, "f": 12, "n": 10, "r": 13, "t": 9, "v": 11,
    "\\": 92, '"': 34, "'": 39, "\n": 10,
}

_KEYWORDS = {"nil", "true", "false"}
_RESERVED = {
    "and", "break", "do", "else", "elseif", "end", "for", "function", "goto", "if", "in",
    "local", "not", "or", "repeat", "return", "then", "until", "while",
}


class _Token:
    __slots__ = ("kind", "text", "line")

    def __init__(self, kind: str, text: str, line: int):
        self.kind = kind
        self.text = text
        self.line = line

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Token({self.kind}, {self.text!r}, line {self.line})"


def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    pos = 0
    line = 1
    end = len(text)
    match = _TOKEN_RE.match
    while pos < end:
        m = match(text, pos)
        if m is None:
            snippet = text[pos : pos + 20].split("\n", 1)[0]
            raise SavedVariablesError(f"unexpected input {snippet!r}", line=line)
        kind = m.lastgroup
        chunk = m.group(0)
        if kind == "eq":  # only produced inside block_comment
            kind = "block_comment"
        if kind not in ("ws", "block_comment", "line_comment"):
            tokens.append(_Token(kind, chunk, line))
        line += chunk.count("\n")
        pos = m.end()
    tokens.append(_Token("eof", "", line))
    return tokens


def _unescape(raw: str, line: int, limits: ParseLimits) -> str:
    body = raw[1:-1]
    if "\\" not in body:
        out = body
    else:
        buf = bytearray()
        i = 0
        n = len(body)
        while i < n:
            ch = body[i]
            if ch != "\\":
                buf.extend(ch.encode("utf-8"))
                i += 1
                continue
            i += 1
            if i >= n:
                raise SavedVariablesError("dangling escape in string", line=line)
            esc = body[i]
            if esc == "\r":
                buf.append(10)
                i += 2 if i + 1 < n and body[i + 1] == "\n" else 1
            elif esc in _SIMPLE_ESCAPES:
                buf.append(_SIMPLE_ESCAPES[esc])
                i += 1
            elif esc.isdigit():
                j = i
                while j < n and j - i < 3 and body[j].isdigit():
                    j += 1
                code = int(body[i:j])
                if code > 255:
                    raise SavedVariablesError("decimal escape out of range", line=line)
                buf.append(code)
                i = j
            elif esc == "x" and re.fullmatch(r"[0-9a-fA-F]{2}", body[i + 1 : i + 3]):
                buf.append(int(body[i + 1 : i + 3], 16))
                i += 3
            else:
                raise SavedVariablesError(f"invalid escape \\{esc}", line=line)
        out = buf.decode("utf-8", errors="replace")
    if len(out.encode("utf-8")) > limits.max_string_bytes:
        raise SavedVariablesError("string exceeds size limit", line=line)
    return out


def _number(text: str, line: int, limits: ParseLimits) -> int | float:
    neg = text.startswith("-")
    digits = text[1:] if neg else text
    try:
        if digits[:2] in ("0x", "0X"):
            value: int | float = int(digits, 16)
        elif any(c in digits for c in ".eE"):
            value = float(digits)
        else:
            value = int(digits)
    except ValueError as exc:  # pragma: no cover - regex guarantees shape
        raise SavedVariablesError(f"invalid number {text!r}", line=line) from exc
    if neg:
        value = -value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SavedVariablesError("non-finite number", line=line)
    elif abs(value) > limits.max_abs_integer:
        raise SavedVariablesError("integer out of range", line=line)
    return value


class _Parser:
    def __init__(self, tokens: list[_Token], limits: ParseLimits):
        self.tokens = tokens
        self.pos = 0
        self.limits = limits
        self.values = 0

    def peek(self) -> _Token:
        return self.tokens[self.pos]

    def take(self) -> _Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, kind: str, text: str | None = None) -> _Token:
        tok = self.take()
        if tok.kind != kind or (text is not None and tok.text != text):
            want = text or kind
            raise SavedVariablesError(f"expected {want!r}, found {tok.text or tok.kind!r}", line=tok.line)
        return tok

    def count(self, line: int) -> None:
        self.values += 1
        if self.values > self.limits.max_values:
            raise SavedVariablesError("too many values", line=line)

    def parse_file(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        while self.peek().kind != "eof":
            name_tok = self.expect("name")
            if name_tok.text in _KEYWORDS or name_tok.text in _RESERVED:
                raise SavedVariablesError(f"unexpected keyword {name_tok.text!r}", line=name_tok.line)
            self.expect("punct", "=")
            value = self.parse_value(depth=0)
            if value is not None:
                result[name_tok.text] = value
            else:
                result.pop(name_tok.text, None)
            if self.peek().kind == "punct" and self.peek().text == ";":
                self.take()
        return result

    def parse_value(self, depth: int) -> Any:
        tok = self.take()
        self.count(tok.line)
        if tok.kind == "string":
            return _unescape(tok.text, tok.line, self.limits)
        if tok.kind == "number":
            return _number(tok.text, tok.line, self.limits)
        if tok.kind == "name":
            if tok.text == "nil":
                return None
            if tok.text == "true":
                return True
            if tok.text == "false":
                return False
            raise SavedVariablesError(f"identifiers are not allowed as values ({tok.text!r})", line=tok.line)
        if tok.kind == "punct" and tok.text == "{":
            if depth + 1 > self.limits.max_depth:
                raise SavedVariablesError("tables nested too deeply", line=tok.line)
            return self.parse_table(depth + 1)
        raise SavedVariablesError(f"unexpected {tok.text or tok.kind!r}", line=tok.line)

    def parse_table(self, depth: int) -> Any:
        entries: dict[Any, Any] = {}
        next_index = 1
        while True:
            tok = self.peek()
            if tok.kind == "punct" and tok.text == "}":
                self.take()
                break
            if tok.kind == "punct" and tok.text == "[":
                self.take()
                key = self.parse_value(depth)
                if key is None:
                    raise SavedVariablesError("nil table key", line=tok.line)
                if isinstance(key, (dict, list)):
                    raise SavedVariablesError("table used as a table key", line=tok.line)
                if isinstance(key, float) and key.is_integer():
                    key = int(key)
                self.expect("punct", "]")
                self.expect("punct", "=")
                value = self.parse_value(depth)
            elif (
                tok.kind == "name"
                and tok.text not in _KEYWORDS
                and self.tokens[self.pos + 1].kind == "punct"
                and self.tokens[self.pos + 1].text == "="
            ):
                self.take()
                self.take()
                key = tok.text
                value = self.parse_value(depth)
            else:
                key = next_index
                next_index += 1
                value = self.parse_value(depth)
            if value is None:
                entries.pop(key, None)
            else:
                entries[key] = value
            sep = self.peek()
            if sep.kind == "punct" and sep.text in (",", ";"):
                self.take()
            elif not (sep.kind == "punct" and sep.text == "}"):
                raise SavedVariablesError(f"expected ',' or '}}', found {sep.text or sep.kind!r}", line=sep.line)
        return _table_to_python(entries)


def _table_to_python(entries: dict[Any, Any]) -> Any:
    if not entries:
        return []
    n = len(entries)
    if all(type(k) is int for k in entries) and min(entries) == 1 and max(entries) == n:
        return [entries[i] for i in range(1, n + 1)]
    return entries


def parse_savedvariables(data: bytes | str, limits: ParseLimits | None = None) -> dict[str, Any]:
    """Parse a SavedVariables file into ``{global_name: value}``.

    Raises :class:`SavedVariablesError` for anything outside the data-only grammar or the limits.
    """
    limits = limits or ParseLimits()
    if isinstance(data, bytes):
        if len(data) > limits.max_bytes:
            raise SavedVariablesError("file exceeds size limit")
        if data.startswith(b"\xef\xbb\xbf"):
            data = data[3:]
        text = data.decode("utf-8", errors="replace")
    else:
        if len(data.encode("utf-8")) > limits.max_bytes:
            raise SavedVariablesError("file exceeds size limit")
        text = data.lstrip("﻿")
    tokens = _tokenize(text)
    return _Parser(tokens, limits).parse_file()
