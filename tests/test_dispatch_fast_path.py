"""Tests for the dispatch fast-path (non-speckit skill/agent early-exit).

Verifies that non-speckit Skill/Agent invocations exit 0 immediately without
loading nodes.json, and that the TTY guard prints a hint instead of blocking.
"""

from __future__ import annotations

import io
import json
import sys
from unittest.mock import patch, MagicMock

import pytest

from speckit_gate.dispatch import dispatch, _fast_path_exit


# ---------------------------------------------------------------------------
# _fast_path_exit unit tests
# ---------------------------------------------------------------------------

class TestFastPathExit:
    def test_non_speckit_skill_returns_true(self):
        payload = {"tool_input": {"skill": "bash"}}
        assert _fast_path_exit("PreToolUse", payload) is True

    def test_speckit_skill_returns_false(self):
        payload = {"tool_input": {"skill": "speckit-plan"}}
        assert _fast_path_exit("PreToolUse", payload) is False

    def test_speckit_dot_skill_returns_false(self):
        payload = {"tool_input": {"skill": "speckit.tasks"}}
        assert _fast_path_exit("PostToolUse", payload) is False

    def test_non_speckit_agent_returns_true(self):
        payload = {"tool_input": {"subagent_type": "coder"}}
        assert _fast_path_exit("PreToolUse", payload) is True

    def test_speckit_agent_returns_false(self):
        payload = {"tool_input": {"subagent_type": "speckit-verify"}}
        assert _fast_path_exit("PreToolUse", payload) is False

    def test_non_speckit_agentType_returns_true(self):
        payload = {"tool_input": {"agentType": "general-purpose"}}
        assert _fast_path_exit("PreToolUse", payload) is True

    def test_no_tool_input_dict_returns_true(self):
        # tool_input is a string — can't be a speckit skill
        assert _fast_path_exit("PreToolUse", {"tool_input": "bare-string"}) is True

    def test_missing_tool_input_returns_true(self):
        assert _fast_path_exit("PreToolUse", {}) is True

    def test_non_tool_event_returns_false(self):
        # UserPromptExpansion and UserPromptSubmit are not fast-path bypassed here
        assert _fast_path_exit("UserPromptSubmit", {}) is False
        assert _fast_path_exit("SomeOtherEvent", {}) is False

    def test_UserPromptExpansion_non_speckit_returns_true(self):
        payload = {"command_name": "bash"}
        assert _fast_path_exit("UserPromptExpansion", payload) is True

    def test_UserPromptExpansion_speckit_returns_false(self):
        payload = {"command_name": "speckit.plan"}
        assert _fast_path_exit("UserPromptExpansion", payload) is False

    def test_UserPromptExpansion_no_command_name_returns_false(self):
        # No command_name → let full path handle it
        assert _fast_path_exit("UserPromptExpansion", {}) is False

    def test_non_speckit_command_name_returns_true(self):
        payload = {"tool_input": {"command_name": "read"}}
        assert _fast_path_exit("PreToolUse", payload) is True

    def test_speckit_command_name_returns_false(self):
        payload = {"tool_input": {"command_name": "speckit-tasks"}}
        assert _fast_path_exit("PreToolUse", payload) is False


# ---------------------------------------------------------------------------
# dispatch() fast-path: non-speckit skill produces no output and no file read
# ---------------------------------------------------------------------------

def _run_dispatch(monkeypatch, payload, phase="pre", nodes_path=None):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    rc = dispatch(phase, nodes_path)
    return rc, out.getvalue()


def test_non_speckit_skill_no_output_no_file_read(monkeypatch, tmp_path):
    """A non-speckit Skill invocation exits 0 with no output and never opens nodes.json."""
    # Write a nodes.json that WOULD fire if loaded
    nodes = tmp_path / "nodes.json"
    nodes.write_text(json.dumps({"plan": {"pre": {"title": "/speckit.plan", "soft": []}}}))

    open_calls: list[str] = []
    real_open = open

    def tracking_open(path, *args, **kwargs):
        open_calls.append(str(path))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", tracking_open)

    rc, output = _run_dispatch(
        monkeypatch,
        {
            "hook_event_name": "PreToolUse",
            "tool_input": {"skill": "bash"},
            "cwd": str(tmp_path),
        },
        nodes_path=str(nodes),
    )
    assert rc == 0
    assert output == ""
    # nodes.json must not have been opened
    nodes_reads = [p for p in open_calls if "nodes.json" in p]
    assert not nodes_reads, f"nodes.json was opened unexpectedly: {nodes_reads}"


def test_non_speckit_agent_no_output(monkeypatch, tmp_path):
    """A non-speckit Agent spawn produces no output."""
    nodes = tmp_path / "nodes.json"
    nodes.write_text(json.dumps({"verify": {"pre": {"title": "/speckit.verify", "soft": []}}}))

    rc, output = _run_dispatch(
        monkeypatch,
        {
            "hook_event_name": "PreToolUse",
            "tool_input": {"subagent_type": "coder"},
            "cwd": str(tmp_path),
        },
        nodes_path=str(nodes),
    )
    assert rc == 0
    assert output == ""


def test_speckit_skill_still_fires(monkeypatch, tmp_path):
    """A speckit Skill invocation is NOT fast-pathed — gate logic runs."""
    nodes = tmp_path / "nodes.json"
    nodes.write_text(json.dumps({
        "_config": {"prefix": "speckit.", "feature_root": "specs"},
        "plan": {"pre": {"title": "/speckit.plan", "soft": [], "hard_missing": ["specs/<feat>/spec.md"]}},
    }))

    rc, output = _run_dispatch(
        monkeypatch,
        {
            "hook_event_name": "PreToolUse",
            "tool_input": {"skill": "speckit-plan"},
            "cwd": str(tmp_path),
        },
        nodes_path=str(nodes),
    )
    assert rc == 0
    # No spec.md → should emit a deny decision
    assert output != "", "Expected gate output for speckit skill invocation"
    decision = json.loads(output)
    assert decision.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


# ---------------------------------------------------------------------------
# dispatch() TTY guard
# ---------------------------------------------------------------------------

def test_dispatch_tty_stdin_prints_hint(monkeypatch, capsys):
    """When stdin is a TTY, dispatch prints a usage hint to stderr and exits 0."""
    tty_stdin = MagicMock()
    tty_stdin.isatty.return_value = True
    monkeypatch.setattr(sys, "stdin", tty_stdin)
    rc = dispatch("pre")
    captured = capsys.readouterr()
    assert rc == 0
    assert "dry-run" in captured.err
    assert "dispatch" in captured.err


def test_dispatch_non_tty_stdin_reads_payload(monkeypatch, tmp_path):
    """When stdin is not a TTY, dispatch reads the payload normally (no hint)."""
    nodes = tmp_path / "nodes.json"
    nodes.write_text(json.dumps({"plan": {"pre": {"title": "/speckit.plan", "soft": []}}}))

    stdin_mock = io.StringIO(json.dumps({"hook_event_name": "PreToolUse", "tool_input": {"skill": "bash"}}))
    # StringIO.isatty() returns False by default
    monkeypatch.setattr(sys, "stdin", stdin_mock)
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)

    rc = dispatch("pre", str(nodes))
    assert rc == 0
