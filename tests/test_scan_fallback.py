"""Tests for scan.py fallback path and pattern extraction."""

from __future__ import annotations

import os

import pytest

from speckit_gate.scan import scan_project, _extract_commands_from_file


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def test_extract_commands_from_speckit_slash_syntax(tmp_path):
    f = tmp_path / "skill.md"
    f.write_text("Run /speckit.plan and /speckit.tasks after /speckit.specify.")
    cmds = _extract_commands_from_file(str(f))
    assert "plan" in cmds
    assert "tasks" in cmds
    assert "specify" in cmds


def test_extract_commands_from_hyphen_syntax(tmp_path):
    f = tmp_path / "skill.md"
    f.write_text("Use $speckit-verify-tasks to check completions.")
    cmds = _extract_commands_from_file(str(f))
    assert "verify-tasks" in cmds


def test_extract_commands_returns_empty_on_missing_file():
    cmds = _extract_commands_from_file("/nonexistent/path.md")
    assert cmds == []


def test_extract_commands_deduplicated(tmp_path):
    f = tmp_path / "skill.md"
    f.write_text("/speckit.plan /speckit.plan /speckit.plan")
    cmds = _extract_commands_from_file(str(f))
    assert cmds.count("plan") == 1


def test_scan_project_empty_dir(tmp_path):
    cmds = scan_project(str(tmp_path))
    assert isinstance(cmds, list)


def test_scan_project_finds_commands(tmp_path):
    skills_dir = tmp_path / ".claude" / "skills"
    skills_dir.mkdir(parents=True)
    skill = skills_dir / "example.md"
    skill.write_text("Run /speckit.specify then /speckit.plan.")
    cmds = scan_project(str(tmp_path))
    assert "specify" in cmds
    assert "plan" in cmds


def test_scan_fixture_project():
    """The fixture project has a .specify directory but no skills.
    scan should return a list (possibly populated from .specify/integration.json)."""
    cmds = scan_project(FIXTURE_DIR)
    assert isinstance(cmds, list)
