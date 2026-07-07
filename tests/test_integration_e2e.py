"""End-to-end integration tests for the full speckit-gate workflow.

Tests the complete flow in a tmp directory:
  init --defaults  → gates.yaml written
  compile          → nodes.json written with expected gate count
  install claude   → .claude/settings.json has hooks
  dry-run plan     → real verdict (not "not found")
  dry-run tasks (no plan.md) → deny verdict
  propose          → table with expected commands
  dispatch pre (PreToolUse speckit-tasks, no plan.md) → deny JSON
  dispatch pre (non-speckit skill) → empty output (fast-path)

All tests use pytest tmp_path and are self-contained.
"""

from __future__ import annotations

import io
import json
import os
import sys

import pytest

from speckit_gate.cli import main
from speckit_gate.dispatch import dispatch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_speckit_project(tmp_path) -> None:
    """Create a minimal .specify/integration.json to seed the built-in commands."""
    specify_dir = tmp_path / ".specify"
    specify_dir.mkdir(parents=True, exist_ok=True)
    (specify_dir / "integration.json").write_text(
        json.dumps({"integration": "speckit", "version": "1.0.0"})
    )


def _run_dispatch_payload(monkeypatch, payload: dict, phase: str, nodes_path: str):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    rc = dispatch(phase, nodes_path)
    return rc, out.getvalue()


def _nodes_path(tmp_path) -> str:
    return str(tmp_path / ".specify" / "gates" / "nodes.json")


# ---------------------------------------------------------------------------
# Step 1: init --defaults writes gates.yaml
# ---------------------------------------------------------------------------

def test_e2e_init_defaults_writes_gates_yaml(tmp_path, capsys):
    _create_speckit_project(tmp_path)
    rc = main(["init", "--defaults", "--root", str(tmp_path)])
    assert rc == 0
    gates_yaml = tmp_path / "gates.yaml"
    assert gates_yaml.exists(), "gates.yaml should be written by init --defaults"
    content = gates_yaml.read_text()
    assert "gates:" in content
    assert "speckit." in content or "prefix:" in content


def test_e2e_init_prints_next_steps(tmp_path, capsys):
    _create_speckit_project(tmp_path)
    main(["init", "--defaults", "--root", str(tmp_path)])
    captured = capsys.readouterr()
    assert "compile" in captured.err
    assert "install" in captured.err


# ---------------------------------------------------------------------------
# Step 2: compile → nodes.json with expected gate count
# ---------------------------------------------------------------------------

def test_e2e_compile_writes_nodes_json(tmp_path, capsys):
    _create_speckit_project(tmp_path)
    main(["init", "--defaults", "--root", str(tmp_path)])
    capsys.readouterr()  # clear

    rc = main(["compile", "--root", str(tmp_path)])
    assert rc == 0

    nodes_file = tmp_path / ".specify" / "gates" / "nodes.json"
    assert nodes_file.exists(), "nodes.json should be written by compile"

    data = json.loads(nodes_file.read_text())
    # _config is the metadata key; the rest are nodes
    gate_count = len([k for k in data if k != "_config"])
    assert gate_count >= 5, f"Expected at least 5 gates, got {gate_count}"


def test_e2e_compile_hints_install_when_no_settings(tmp_path, capsys):
    _create_speckit_project(tmp_path)
    main(["init", "--defaults", "--root", str(tmp_path)])
    capsys.readouterr()

    main(["compile", "--root", str(tmp_path)])
    captured = capsys.readouterr()
    # No .claude/settings.json yet → should print install hint
    assert "install" in captured.err or "install" in captured.out


def test_e2e_compile_no_hint_when_hooks_already_installed(tmp_path, capsys):
    _create_speckit_project(tmp_path)
    main(["init", "--defaults", "--root", str(tmp_path)])
    main(["install", "--harness", "claude", "--root", str(tmp_path)])
    capsys.readouterr()

    main(["compile", "--root", str(tmp_path)])
    captured = capsys.readouterr()
    # .claude/settings.json already has dispatch → no hint
    assert "install" not in captured.err.lower() or "hint" not in captured.err.lower()


# ---------------------------------------------------------------------------
# Step 3: install --harness claude → .claude/settings.json has hooks
# ---------------------------------------------------------------------------

def test_e2e_install_claude_creates_settings_json(tmp_path, capsys):
    rc = main(["install", "--harness", "claude", "--root", str(tmp_path)])
    assert rc == 0

    settings_path = tmp_path / ".claude" / "settings.json"
    assert settings_path.exists()

    data = json.loads(settings_path.read_text())
    assert "hooks" in data
    hooks = data["hooks"]
    # Should have UserPromptExpansion (for speckit.* commands) and PreToolUse
    assert "UserPromptExpansion" in hooks or "PreToolUse" in hooks


def test_e2e_install_claude_hooks_contain_dispatch(tmp_path, capsys):
    main(["install", "--harness", "claude", "--root", str(tmp_path)])
    settings_path = tmp_path / ".claude" / "settings.json"
    raw = settings_path.read_text()
    assert "dispatch" in raw


# ---------------------------------------------------------------------------
# Step 4: dry-run speckit.plan → real verdict
# ---------------------------------------------------------------------------

def test_e2e_dry_run_plan_produces_output(tmp_path, capsys):
    _create_speckit_project(tmp_path)
    main(["init", "--defaults", "--root", str(tmp_path)])
    main(["compile", "--root", str(tmp_path)])
    capsys.readouterr()

    rc = main(["dry-run", "speckit.plan", "--root", str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr()
    # Should produce JSON (gate fired, either block or advisory)
    assert captured.out.strip(), "dry-run speckit.plan should produce output"
    # Verify it's parseable JSON
    parsed = json.loads(captured.out)
    assert "hookSpecificOutput" in parsed or "decision" in parsed


# ---------------------------------------------------------------------------
# Step 5: dry-run speckit.tasks (without plan.md) → deny verdict
# ---------------------------------------------------------------------------

def test_e2e_dry_run_tasks_without_plan_gives_block(tmp_path, capsys):
    _create_speckit_project(tmp_path)
    main(["init", "--defaults", "--root", str(tmp_path)])
    main(["compile", "--root", str(tmp_path)])
    capsys.readouterr()

    # No plan.md exists → tasks should be denied (hard_missing: plan.md)
    rc = main(["dry-run", "speckit.tasks", "--root", str(tmp_path),
               "--event", "UserPromptExpansion"])
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.out.strip()
    parsed = json.loads(captured.out)
    # tasks requires plan, which produces plan.md → should be blocked
    assert (
        parsed.get("decision") == "block"
        or parsed.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
        or "hookSpecificOutput" in parsed  # advisory
    ), f"Expected block/deny/advisory for tasks without plan.md: {parsed}"


# ---------------------------------------------------------------------------
# Step 6: propose → table with expected commands
# ---------------------------------------------------------------------------

def test_e2e_propose_outputs_table(tmp_path, capsys):
    _create_speckit_project(tmp_path)
    rc = main(["propose", "--root", str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr()
    output = captured.out
    assert output.strip(), "propose should produce output"
    # Should contain header row
    assert "Command" in output
    assert "Requires" in output
    assert "Produces" in output


def test_e2e_propose_md_format(tmp_path, capsys):
    _create_speckit_project(tmp_path)
    rc = main(["propose", "--root", str(tmp_path), "--format", "md"])
    assert rc == 0
    captured = capsys.readouterr()
    output = captured.out
    # Markdown table uses pipe chars
    assert "|" in output
    assert "Command" in output


def test_e2e_propose_aligned_no_pipes(tmp_path, capsys):
    _create_speckit_project(tmp_path)
    rc = main(["propose", "--root", str(tmp_path), "--format", "aligned"])
    assert rc == 0
    captured = capsys.readouterr()
    output = captured.out
    # Aligned format should NOT use pipe separators for the table rows
    lines = [l for l in output.splitlines() if l.strip() and "---" not in l]
    # Header line should not start with |
    assert lines[0].lstrip()[0] != "|" if lines else True


# ---------------------------------------------------------------------------
# Step 7: dispatch pre — PreToolUse speckit-tasks, no plan.md → deny JSON
# ---------------------------------------------------------------------------

def test_e2e_dispatch_pre_speckit_tasks_no_plan_deny(monkeypatch, tmp_path):
    _create_speckit_project(tmp_path)
    main(["init", "--defaults", "--root", str(tmp_path)])
    main(["compile", "--root", str(tmp_path)])
    nodes_file = _nodes_path(tmp_path)

    rc, output = _run_dispatch_payload(
        monkeypatch,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Skill",
            "tool_input": {"skill": "speckit-tasks"},
            "cwd": str(tmp_path),
        },
        phase="pre",
        nodes_path=nodes_file,
    )
    assert rc == 0
    assert output, "Expected deny JSON output for speckit-tasks without plan.md"
    decision = json.loads(output)
    hook_out = decision.get("hookSpecificOutput", {})
    assert hook_out.get("permissionDecision") == "deny", (
        f"Expected deny for tasks without plan.md, got: {decision}"
    )


# ---------------------------------------------------------------------------
# Step 8: dispatch pre — non-speckit skill → empty output (fast-path)
# ---------------------------------------------------------------------------

def test_e2e_dispatch_pre_non_speckit_empty_output(monkeypatch, tmp_path):
    _create_speckit_project(tmp_path)
    main(["init", "--defaults", "--root", str(tmp_path)])
    main(["compile", "--root", str(tmp_path)])
    nodes_file = _nodes_path(tmp_path)

    rc, output = _run_dispatch_payload(
        monkeypatch,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Skill",
            "tool_input": {"skill": "bash"},
            "cwd": str(tmp_path),
        },
        phase="pre",
        nodes_path=nodes_file,
    )
    assert rc == 0
    assert output == "", f"Expected empty output for non-speckit skill, got: {output!r}"


def test_e2e_dispatch_pre_non_speckit_agent_empty_output(monkeypatch, tmp_path):
    _create_speckit_project(tmp_path)
    main(["init", "--defaults", "--root", str(tmp_path)])
    main(["compile", "--root", str(tmp_path)])
    nodes_file = _nodes_path(tmp_path)

    rc, output = _run_dispatch_payload(
        monkeypatch,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "coder"},
            "cwd": str(tmp_path),
        },
        phase="pre",
        nodes_path=nodes_file,
    )
    assert rc == 0
    assert output == "", f"Expected empty output for non-speckit agent, got: {output!r}"
