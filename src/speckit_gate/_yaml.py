"""Minimal YAML parser for the subset used in gates.yaml files.

gates.yaml uses only:
  - top-level mappings
  - nested mappings (2-space indent)
  - string scalars
  - boolean scalars (true/false)
  - integer scalars
  - flow sequences: [item1, item2, ...]  (single-line only)
  - block sequences: - item
  - block scalars: >-, >, |, |-
  - comments: # ...

No pyyaml dependency.  This parser handles the gates.yaml schema only.
"""

from __future__ import annotations

import re
from typing import Any


class ParseError(Exception):
    pass


def load_yaml(text: str) -> Any:
    """Parse a gates.yaml string into a Python dict."""
    lines = text.splitlines()
    result, _ = _parse_block(lines, 0, -1)
    return result


def _strip_comment(line: str) -> str:
    """Remove inline # comment, respecting single/double quoted strings."""
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:i].rstrip()
    return line


def _get_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _parse_scalar(s: str) -> Any:
    s = s.strip()
    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        return s[1:-1]
    if s.startswith("'") and s.endswith("'") and len(s) >= 2:
        return s[1:-1]
    if s.lower() in ("true", "yes"):
        return True
    if s.lower() in ("false", "no"):
        return False
    if s.lower() in ("null", "~", ""):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    return s


def _parse_flow_sequence(s: str) -> list:
    """Parse an inline flow sequence: [item1, item2, ...]"""
    s = s.strip()
    if not (s.startswith("[") and s.endswith("]")):
        return [_parse_scalar(s)]
    inner = s[1:-1].strip()
    if not inner:
        return []
    # Split on commas, respecting nested brackets and quotes
    items = []
    depth = 0
    current = []
    in_single = False
    in_double = False
    for ch in inner:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
            elif ch == "," and depth == 0:
                items.append(_parse_scalar("".join(current).strip()))
                current = []
                continue
        current.append(ch)
    if current:
        items.append(_parse_scalar("".join(current).strip()))
    return items


def _parse_block_scalar(lines: list[str], start: int, indicator: str) -> tuple[str, int]:
    """Parse a block scalar (>-, >, |, |-) starting after the indicator line.

    Returns (text, next_line_index).
    'indicator' is '>' or '|' (strip/keep distinction; we fold for > and
    preserve for |, always strip trailing newlines for - variants).
    """
    i = start
    n = len(lines)

    # Determine indent from first non-empty content line
    content_indent = None
    collected = []
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            collected.append("")
            i += 1
            continue
        line_indent = _get_indent(line)
        if content_indent is None:
            content_indent = line_indent
        if line_indent < content_indent:
            break
        collected.append(line[content_indent:])
        i += 1

    if not collected:
        return "", i

    # Fold (>) or preserve (|)
    if indicator.startswith(">"):
        # Fold: join non-empty lines with space, blank lines become newlines
        parts = []
        for j, part in enumerate(collected):
            if part == "":
                parts.append("\n")
            else:
                if parts and not parts[-1].endswith("\n"):
                    parts.append(" " + part)
                else:
                    parts.append(part)
        text = "".join(parts).strip()
    else:
        text = "\n".join(collected).rstrip("\n")

    return text, i


def _parse_block(lines: list[str], start: int, parent_indent: int) -> tuple[Any, int]:
    """Parse a block starting at line `start`."""
    i = start
    n = len(lines)

    # Skip blank/comment lines
    while i < n and (not lines[i].strip() or lines[i].strip().startswith("#")):
        i += 1
    if i >= n:
        return None, i

    first_line = _strip_comment(lines[i])
    first_stripped = first_line.strip()

    # Sequence block?
    if first_stripped.startswith("- ") or first_stripped == "-":
        return _parse_sequence(lines, i, parent_indent)

    # Mapping block?
    if ":" in first_stripped:
        return _parse_mapping(lines, i, parent_indent)

    return _parse_scalar(first_stripped), i + 1


def _parse_mapping(lines: list[str], start: int, parent_indent: int) -> tuple[dict, int]:
    i = start
    n = len(lines)
    result: dict = {}

    # Determine this block's indent from first real line
    while i < n and (not lines[i].strip() or lines[i].strip().startswith("#")):
        i += 1
    if i >= n:
        return result, i

    block_indent = _get_indent(_strip_comment(lines[i]))

    while i < n:
        raw = lines[i]
        line = _strip_comment(raw)
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        indent = _get_indent(line)
        if indent < block_indent:
            break

        if indent > block_indent:
            # Should not happen in well-formed YAML; skip
            i += 1
            continue

        if ":" not in stripped:
            i += 1
            continue

        colon_pos = stripped.index(":")
        key = stripped[:colon_pos].strip()
        value_part = stripped[colon_pos + 1:].strip()

        i += 1

        if not value_part or value_part.startswith("#"):
            # Value is on next lines (block scalar, nested mapping, or sequence)
            j = i
            while j < n and (not lines[j].strip() or lines[j].strip().startswith("#")):
                j += 1
            if j >= n:
                result[key] = None
                i = j
                continue
            next_line = _strip_comment(lines[j])
            next_stripped = next_line.strip()
            next_indent = _get_indent(next_line)
            if next_indent <= block_indent:
                result[key] = None
                i = j
                continue
            if next_stripped.startswith("- ") or next_stripped == "-":
                val, i = _parse_sequence(lines, j, block_indent)
            else:
                val, i = _parse_mapping(lines, j, block_indent)
            result[key] = val
        elif value_part.startswith("["):
            # Flow sequence
            result[key] = _parse_flow_sequence(value_part)
            # If the flow sequence spans multiple lines, skip (not supported; gates.yaml uses single-line)
        elif value_part in (">", ">-", "|", "|-"):
            # Block scalar
            indicator = value_part
            val, i = _parse_block_scalar(lines, i, indicator)
            result[key] = val
        else:
            result[key] = _parse_scalar(value_part)

    return result, i


def _parse_sequence(lines: list[str], start: int, parent_indent: int) -> tuple[list, int]:
    i = start
    n = len(lines)
    result: list = []

    while i < n:
        raw = lines[i]
        line = _strip_comment(raw)
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        indent = _get_indent(line)
        if indent <= parent_indent and i > start:
            break

        if not stripped.startswith("- ") and stripped != "-":
            break

        item_text = stripped[2:].strip() if stripped.startswith("- ") else ""
        i += 1

        if not item_text or item_text.startswith("#"):
            # Block value follows
            j = i
            while j < n and (not lines[j].strip() or lines[j].strip().startswith("#")):
                j += 1
            if j >= n or _get_indent(_strip_comment(lines[j])) <= indent:
                result.append(None)
                i = j
                continue
            val, i = _parse_block(lines, j, indent)
            result.append(val)
        elif item_text.startswith("["):
            # Inline flow sequence as item
            result.append(_parse_flow_sequence(item_text))
        else:
            result.append(_parse_scalar(item_text))

    return result, i
