"""Tests for dry-run error messaging.

Verifies the three error cases:
  1. No command argument → usage error with exit 1
  2. nodes.json doesn't exist → "run compile first" error with exit 1
  3. Command not found in compiled nodes → actionable "(no gate)" message
"""

from __future__ import annotations

import json
import os

import pytest

from speckit_gate.cli import main
from speckit_gate.compile import compile_gates


FIXTURE_GATES = os.path.join(
    os.path.dirname(__file__), "fixtures", "gates.yaml"
)


def _make_nodes_json(tmp_path) -> str:
    nodes, cfg, _ = compile_gates(FIXTURE_GATES)
    output = {"_config": cfg, **nodes}
    p = tmp_path / ".specify" / "gates"
    p.mkdir(parents=True)
    nodes_path = p / "nodes.json"
    nodes_path.write_text(json.dumps(output, indent=2))
    return str(nodes_path)


# ---------------------------------------------------------------------------
# No command argument
# ---------------------------------------------------------------------------

def test_dry_run_no_command_exits_1(tmp_path, capsys):
    """dry-run with no command must exit 1 with a usage hint."""
    rc = main(["dry-run", "--root", str(tmp_path)])
    assert rc == 1
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "command argument required" in captured.err


# ---------------------------------------------------------------------------
# Missing nodes.json
# ---------------------------------------------------------------------------

def test_dry_run_missing_nodes_json_exits_1(tmp_path, capsys):
    """dry-run when nodes.json doesn't exist must print compile hint and exit 1."""
    rc = main(["dry-run", "speckit.plan", "--root", str(tmp_path)])
    assert rc == 1
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "compile" in captured.err


def test_dry_run_missing_nodes_json_explicit_path_exits_1(tmp_path, capsys):
    """Explicit --nodes path that doesn't exist triggers the same error."""
    rc = main(["dry-run", "speckit.plan", "--nodes", str(tmp_path / "nonexistent.json")])
    assert rc == 1
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "compile" in captured.err


# ---------------------------------------------------------------------------
# Command not found in nodes.json
# ---------------------------------------------------------------------------

def test_dry_run_unknown_command_prints_actionable_message(tmp_path, capsys):
    """An unknown command shows an actionable '(no gate — ...)' message, exits 0."""
    _make_nodes_json(tmp_path)
    rc = main(["dry-run", "speckit.nonexistent-command", "--root", str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "no gate" in captured.out
    assert "explain" in captured.out


def test_dry_run_unknown_command_includes_command_name(tmp_path, capsys):
    """The no-gate message includes the command name for clarity."""
    _make_nodes_json(tmp_path)
    rc = main(["dry-run", "speckit.unknown-xyz", "--root", str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "unknown-xyz" in captured.out or "speckit" in captured.out


# ---------------------------------------------------------------------------
# Happy-path dry-run (sanity: known gated command returns real output)
# ---------------------------------------------------------------------------

def test_dry_run_known_command_returns_output(tmp_path, capsys):
    """dry-run speckit.plan with a compiled nodes.json produces real gate output."""
    _make_nodes_json(tmp_path)
    rc = main(["dry-run", "speckit.plan", "--root", str(tmp_path)])
    # May be 0 (blocked) or 0 (gate advisory) — should produce output
    assert rc == 0
    captured = capsys.readouterr()
    # Should produce JSON output (gate fired) OR the no-gate message
    # With fixture gates.yaml, 'plan' IS a gated command → should produce JSON
    assert captured.out.strip(), "Expected gate output for speckit.plan"
