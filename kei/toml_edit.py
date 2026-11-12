"""A TOML value editor that edits text, not a parsed tree: one value changes and every comment, every other value
and every other byte of the file stays as it was. Standard library only (tomllib reads TOML but cannot write it).

The editor walks the file once. A key's value is found by counting brackets and string quotes (basic, literal and
multi-line), so a value that spans lines is found whole, and a # inside a quoted value is not a comment."""
from __future__ import annotations

import json
import re

_NAME = r"[A-Za-z0-9_.-]+"
_TABLE = re.compile(rf"^\s*\[\s*({_NAME})\s*\]\s*(#.*)?$")
_ARRAY = re.compile(rf"^\s*\[\[\s*({_NAME})\s*\]\]\s*(#.*)?$")
_CTABLE = re.compile(rf"^\s*#\s*\[\s*({_NAME})\s*\]\s*(#.*)?$")      # a commented-out table header
_KEY = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*=\s*")
_CKEY = re.compile(r"^(\s*)#\s?(\s*([A-Za-z0-9_-]+)\s*=.*)$")         # a commented-out key line


class TomlEditError(ValueError):
    """The edit cannot be made. The message names the table and the key."""


def _newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _value_end(text: str, i: int) -> int:
    """The end of the value that starts at i: brackets and strings counted, trailing spaces left out."""
    start, n, depth = i, len(text), 0
    while i < n:
        if text.startswith('"""', i) or text.startswith("'''", i):
            q = text[i:i + 3]
            j = i + 3
            while True:
                j = text.find(q, j)
                if j < 0:
                    raise TomlEditError("a multi-line string is not closed")
                if q == "'''" or (len(text[:j]) - len(text[:j].rstrip("\\"))) % 2 == 0:
                    break
                j += 1
            i = j + 3
            while i < n and text[i] == q[0]:   # up to two quotes may close the string's own content
                i += 1
            continue
        c = text[i]
        if c == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
            i += 1
            continue
        if c == "'":
            j = text.find("'", i + 1)
            i = (j if j >= 0 else n) + 1
            continue
        if c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
        elif c == "#":
            if depth <= 0:
                break
            j = text.find("\n", i)
            i = j if j >= 0 else n
            continue
        elif c in "\r\n" and depth <= 0:
            break
        i += 1
    end = min(i, n)
    while end > start and text[end - 1] in " \t":
        end -= 1
    return end


def _line_end(text: str, i: int) -> int:
    """The index just after the newline of the line that holds i (or the end of the text)."""
    j = text.find("\n", i)
    return len(text) if j < 0 else j + 1


def _walk(text: str) -> list[dict]:
    """Every header, key and commented key or header, in order, with their spans."""
    items, pos, n = [], 0, len(text)
    while pos < n:
        eol = _line_end(text, pos)
        line = text[pos:eol].rstrip("\r\n")
        for kind, rx in (("array", _ARRAY), ("table", _TABLE), ("ctable", _CTABLE)):
            m = rx.match(line)
            if m:
                items.append({"type": kind, "name": m.group(1), "start": pos, "end": eol})
                break
        else:
            m = _KEY.match(line)
            if m:
                vstart = pos + m.end()
                vend = _value_end(text, vstart)
                end = _line_end(text, vend)
                items.append({"type": "key", "name": m.group(1), "start": pos, "vstart": vstart, "vend": vend,
                              "end": end})
                pos = end
                continue
            m = _CKEY.match(line)
            if m:
                items.append({"type": "ckey", "name": m.group(3), "start": pos, "end": eol})
        pos = eol
    return items


def _region(text: str, table: str, index: int | None) -> tuple[dict, list[dict], int] | None:
    """The header of [table] (or the index-th [[table]]), the items after it, and where its region ends."""
    items = _walk(text)
    kind = "table" if index is None else "array"
    headers = [k for k, it in enumerate(items) if it["type"] == kind and it["name"] == table]
    if index is not None and index >= len(headers):
        return None
    if not headers:
        return None
    k = headers[0 if index is None else index]
    body = []
    end = len(text)
    for it in items[k + 1:]:
        if it["type"] in ("table", "array", "ctable"):
            end = it["start"]
            break
        body.append(it)
    return items[k], body, end


def find_value(text: str, table: str, key: str, index: int | None = None) -> tuple[int, int] | None:
    """The span (start, end) of key's value in [table], or in the index-th [[table]]; None when absent."""
    r = _region(text, table, index)
    if r is None:
        return None
    for it in r[1]:
        if it["type"] == "key" and it["name"] == key:
            return it["vstart"], it["vend"]
    return None


def _uncomment(text: str, start: int, end: int) -> str:
    line = text[start:end]
    body = line.rstrip("\r\n")
    m = re.match(r"^(\s*)#\s?(.*)$", body, re.S)
    return text[:start] + m.group(1) + m.group(2) + line[len(body):] + text[end:]


def set_value(text: str, table: str, key: str, toml_value: str, index: int | None = None) -> str:
    """Replace key's value in [table] (or the index-th [[table]]). An absent key: a commented example line in that
    table is uncommented in place, else the line is added at the end of the table. An absent table: a commented
    header is uncommented, else the table is added at the end of the file."""
    nl = _newline(text)
    span = find_value(text, table, key, index)
    if span is not None:
        return text[:span[0]] + toml_value + text[span[1]:]
    r = _region(text, table, index)
    if r is None:
        if index is not None:
            raise TomlEditError(f"there is no [[{table}]] number {index + 1}")
        chead = next((it for it in _walk(text) if it["type"] == "ctable" and it["name"] == table), None)
        if chead is not None:
            return set_value(_uncomment(text, chead["start"], chead["end"]), table, key, toml_value)
        body = text if not text or text.endswith(("\n", "\r\n")) else text + nl
        return f"{body}{nl}[{table}]{nl}{key} = {toml_value}{nl}"
    header, body, _ = r
    ckey = next((it for it in body if it["type"] == "ckey" and it["name"] == key), None)
    if ckey is not None:
        uncommented = _uncomment(text, ckey["start"], ckey["end"])
        span = find_value(uncommented, table, key, index)
        if span is not None:
            return uncommented[:span[0]] + toml_value + uncommented[span[1]:]
    keys = [it for it in body if it["type"] == "key"]
    at = keys[-1]["end"] if keys else header["end"]
    prefix = "" if at == 0 or text[at - 1] == "\n" else nl
    return text[:at] + f"{prefix}{key} = {toml_value}{nl}" + text[at:]


def unset_value(text: str, table: str, key: str, index: int | None = None) -> str:
    """Remove the key's line (all its lines, for a value that spans several), so the default applies again."""
    r = _region(text, table, index)
    if r is None:
        return text
    for it in r[1]:
        if it["type"] == "key" and it["name"] == key:
            return text[:it["start"]] + text[it["end"]:]
    return text


def add_table(text: str, block: str) -> str:
    """Add a table (for example a [[critics]] block) at the end of the file, in the file's line endings."""
    nl = _newline(text)
    block = block.replace("\r\n", "\n").replace("\n", nl)
    body = text if not text or text.endswith("\n") else text + nl
    return f"{body}{nl}{block}" + ("" if block.endswith(nl) else nl)


def remove_array_table(text: str, table: str, index: int) -> str:
    """Remove the index-th [[table]] block. Comment lines right before the next header belong to that header and
    stay."""
    r = _region(text, table, index)
    if r is None:
        raise TomlEditError(f"there is no [[{table}]] number {index + 1}")
    header, _, end = r
    lines_end = end
    while True:   # give the comment block that leads the next header back to it
        prev = text.rfind("\n", 0, lines_end - 1) + 1 if lines_end > 0 else 0
        line = text[prev:lines_end].strip()
        if lines_end > header["end"] and line.startswith("#"):
            lines_end = prev
            continue
        break
    return text[:header["start"]] + text[lines_end:]


def format_value(value) -> str:
    """A Python value as a TOML value: text, a whole number, true or false, or a list of those."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(format_value(v) for v in value) + "]"
    raise TomlEditError(f"{value!r} cannot be written as a TOML value")
