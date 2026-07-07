"""Scan a project for spec-kit commands and map them to known gates.

Reads the installed harness config to discover which commands are in use,
then cross-references against known_gates for a prerequisite proposal.
Falls back to a minimal YAML parser for gates.yaml files.
"""

from __future__ import annotations

import json
import os
import re
from typing import Iterator


def _iter_skill_files(root: str) -> Iterator[str]:
    """Yield paths of skill/command files in common harness dirs."""
    candidates = [
        os.path.join(root, ".claude", "skills"),
        os.path.join(root, ".agents", "skills"),
        os.path.join(root, ".specify", "extensions"),
        os.path.join(root, "skills"),
    ]
    for d in candidates:
        if os.path.isdir(d):
            for name in os.listdir(d):
                yield os.path.join(d, name)


def _extract_commands_from_file(path: str) -> list[str]:
    """Extract speckit command names referenced in a skill/markdown file."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return []
    # Match /speckit.foo.bar or speckit-foo-bar patterns
    found = set()
    for m in re.finditer(r"[/\$]speckit[-.]([a-z][a-z0-9.\-]*[a-z0-9]|[a-z])", text):
        cmd = m.group(1).replace(".", "-")
        found.add(cmd)
    return sorted(found)


def scan_project(root: str) -> list[str]:
    """Scan root for spec-kit commands in use. Returns sorted command list."""
    commands: set[str] = set()
    for path in _iter_skill_files(root):
        for cmd in _extract_commands_from_file(path):
            commands.add(cmd)

    # Also check .specify/integration.json for the installed integration key
    integration_json = os.path.join(root, ".specify", "integration.json")
    if os.path.isfile(integration_json):
        try:
            with open(integration_json, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            # If spec-kit is installed we can infer the core command set
            if isinstance(data, dict) and data.get("integration"):
                from speckit_gate.known_gates import BUILTIN_COMMANDS
                commands.update(BUILTIN_COMMANDS)
        except (OSError, ValueError):
            pass

    return sorted(commands)
