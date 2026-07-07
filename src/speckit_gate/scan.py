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

# ---------------------------------------------------------------------------
# Skill-directory layout helpers
# ---------------------------------------------------------------------------

_SKILL_MD_NAME_RE = re.compile(r"^name:\s*(.+)", re.MULTILINE)


def _command_from_skill_dir(dir_path: str) -> str | None:
    """Derive a command name from a skill DIRECTORY.

    Primary: strip the ``speckit-`` prefix from the directory basename.
    Fallback: parse ``name:`` from a ``SKILL.md`` frontmatter block inside
    the directory and strip the prefix from that value.

    Returns ``None`` when no command name can be determined.
    """
    name = os.path.basename(dir_path)
    if name.startswith("speckit-"):
        return name[len("speckit-"):]

    # Fallback: read SKILL.md frontmatter
    skill_md = os.path.join(dir_path, "SKILL.md")
    if os.path.isfile(skill_md):
        try:
            with open(skill_md, "r", encoding="utf-8", errors="replace") as fh:
                # Frontmatter is always at the top; read only the first 512 bytes
                text = fh.read(512)
            m = _SKILL_MD_NAME_RE.search(text)
            if m:
                skill_name = m.group(1).strip()
                if skill_name.startswith("speckit-"):
                    return skill_name[len("speckit-"):]
                return skill_name
        except OSError:
            pass

    return None


def _commands_from_extension_cmd_dir(ext_name: str, cmd_dir: str) -> list[str]:
    """Derive command names from a ``.specify/extensions/<ext>/commands/`` dir.

    Two naming conventions are handled:

    *Dotted APM convention* — filename starts with ``speckit.``:
      ``speckit.tinyspec.md``          → ``tinyspec-tinyspec``  (main ext cmd)
      ``speckit.tinyspec.implement.md`` → ``tinyspec-implement``
      ``speckit.roadmap.brief.md``     → ``roadmap-brief``

    *Plain convention* — bare stem, with or without the ext prefix:
      ``cleanup.md`` in ``cleanup/``        → ``cleanup``
      ``run.md`` in ``critique/``           → ``critique-run``
      ``security-review.md`` in ``security-review/`` → ``security-review``
      ``init.md`` in ``security-review/``  → ``security-review-init``

    Template files (``*-template.md``) are silently skipped.
    """
    commands: list[str] = []
    for fname in sorted(os.listdir(cmd_dir)):
        if not fname.endswith(".md"):
            continue
        stem = fname[:-3]  # strip .md

        # Skip template stubs
        if "-template" in stem:
            continue

        if stem.startswith("speckit."):
            # Dotted APM convention: strip leading "speckit.", replace "." → "-"
            normalized = stem[len("speckit."):].replace(".", "-")
            if normalized == ext_name:
                # Main extension command — use doubled form (APM convention)
                commands.append(f"{ext_name}-{ext_name}")
            else:
                commands.append(normalized)
        else:
            # Plain convention: prefix with ext_name when stem doesn't already
            # start with it
            if stem == ext_name or stem.startswith(f"{ext_name}-"):
                commands.append(stem)
            else:
                commands.append(f"{ext_name}-{stem}")

    return commands


# ---------------------------------------------------------------------------
# Flat-file skill discovery (legacy / other harnesses)
# ---------------------------------------------------------------------------

def _iter_skill_files(root: str) -> Iterator[str]:
    """Yield paths of skill/command *files* in common harness dirs.

    Only FILE entries are yielded.  Subdirectory-layout skills (where each
    skill is a directory rather than a single ``.md`` file) are handled
    separately by ``scan_project`` via ``_command_from_skill_dir``.
    """
    candidates = [
        os.path.join(root, ".claude", "skills"),
        os.path.join(root, ".agents", "skills"),
        os.path.join(root, ".specify", "extensions"),
        os.path.join(root, "skills"),
    ]
    for d in candidates:
        if os.path.isdir(d):
            for name in os.listdir(d):
                p = os.path.join(d, name)
                if os.path.isfile(p):
                    yield p


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


# ---------------------------------------------------------------------------
# Main scan entry point
# ---------------------------------------------------------------------------

def scan_project(root: str) -> list[str]:
    """Scan root for spec-kit commands in use. Returns sorted command list."""
    commands: set[str] = set()

    # ------------------------------------------------------------------
    # 1. Directory-layout skills
    #    .claude/skills/<name>/  or  .agents/skills/<name>/  or  skills/<name>/
    #
    #    Each subdirectory IS one skill; derive the command from the dir
    #    name (strip "speckit-" prefix) rather than reading file content.
    #    Flat .md files in the same directories are also handled here via
    #    content extraction (fallback for non-directory layouts).
    # ------------------------------------------------------------------
    for skills_base in (
        os.path.join(root, ".claude", "skills"),
        os.path.join(root, ".agents", "skills"),
        os.path.join(root, "skills"),
    ):
        if not os.path.isdir(skills_base):
            continue
        for entry in os.listdir(skills_base):
            entry_path = os.path.join(skills_base, entry)
            if os.path.isdir(entry_path):
                cmd = _command_from_skill_dir(entry_path)
                if cmd:
                    commands.add(cmd)
            elif os.path.isfile(entry_path):
                for cmd in _extract_commands_from_file(entry_path):
                    commands.add(cmd)

    # ------------------------------------------------------------------
    # 2. Extension command files
    #    .specify/extensions/<ext>/commands/*.md
    #
    #    Derives command names from the command file names according to the
    #    spec-kit / APM naming conventions.
    # ------------------------------------------------------------------
    ext_base = os.path.join(root, ".specify", "extensions")
    if os.path.isdir(ext_base):
        for ext_name in sorted(os.listdir(ext_base)):
            if ext_name.startswith("."):
                continue
            ext_path = os.path.join(ext_base, ext_name)
            if not os.path.isdir(ext_path):
                continue
            cmd_dir = os.path.join(ext_path, "commands")
            if os.path.isdir(cmd_dir):
                for cmd in _commands_from_extension_cmd_dir(ext_name, cmd_dir):
                    commands.add(cmd)

    # ------------------------------------------------------------------
    # 3. .specify/integration.json — seed with built-ins
    #
    #    When spec-kit itself is confirmed installed we can infer that the
    #    full built-in command set is available, even if no skill files
    #    explicitly reference each command.
    # ------------------------------------------------------------------
    integration_json = os.path.join(root, ".specify", "integration.json")
    if os.path.isfile(integration_json):
        try:
            with open(integration_json, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and data.get("integration"):
                from speckit_gate.known_gates import BUILTIN_COMMANDS
                commands.update(BUILTIN_COMMANDS)
        except (OSError, ValueError):
            pass

    return sorted(commands)
