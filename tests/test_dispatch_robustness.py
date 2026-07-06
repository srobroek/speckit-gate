"""Robustness tests for the dispatcher.

Ported from speckit-dag-hooks/scripts/test_dispatcher_robustness.py.
Tests that the dispatcher never raises on adversarial payloads and
always returns 0.
"""

from __future__ import annotations

import io
import json
import os
import sys

import pytest

from speckit_gate.dispatch import (
    _resolve_command,
    _normalize,
    render_body,
    dispatch,
)
from speckit_gate.resolve import as_str


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


# ---------------------------------------------------------------------------
# as_str coercion
# ---------------------------------------------------------------------------
def test_as_str_coercion():
    assert as_str("ok") == "ok"
    assert as_str(None) == ""
    assert as_str(123) == ""
    assert as_str({"a": 1}) == ""
    assert as_str(["x"]) == ""
    assert as_str(True) == ""


# ---------------------------------------------------------------------------
# _resolve_command must never raise and must return str for any input shape
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "event,payload",
    [
        ("UserPromptExpansion", {"command_name": {"nested": "dict"}}),
        ("UserPromptExpansion", {"command_name": ["a", "list"]}),
        ("UserPromptExpansion", {"command_name": 12345}),
        ("UserPromptExpansion", {"command_name": True}),
        ("UserPromptExpansion", {"command_name": None}),
        ("UserPromptExpansion", {}),
        ("PreToolUse", {"tool_input": "a bare string"}),
        ("PreToolUse", {"tool_input": ["list"]}),
        ("PreToolUse", {"tool_input": 7}),
        ("PreToolUse", {"tool_input": None}),
        ("PreToolUse", {"tool_input": {"skill": {"x": 1}}}),
        ("PreToolUse", {"tool_input": {"command_name": ["y"]}}),
        ("PreToolUse", {"tool_input": {"prompt": 99}}),
        ("PostToolUse", {"tool_input": {"skill": 3.14}}),
        ("PostToolUse", {"tool_input": {"prompt": {"k": "v"}}}),
        ("UserPromptSubmit", {"prompt": {"not": "a string"}}),
        ("UserPromptSubmit", {"prompt": 0}),
        ("UserPromptSubmit", {"prompt": None}),
    ],
)
def test_resolve_command_never_raises_and_returns_str(event, payload):
    result = _resolve_command(event, payload)
    assert isinstance(result, str), f"must return str, got {type(result)!r}"


def test_resolve_command_string_inputs_still_work():
    assert (
        _resolve_command("UserPromptExpansion", {"command_name": "speckit.plan"})
        == "speckit.plan"
    )
    assert (
        _resolve_command("PreToolUse", {"tool_input": {"skill": "speckit-plan"}})
        == "speckit-plan"
    )
    assert (
        _resolve_command("UserPromptSubmit", {"prompt": "run /speckit.plan please"})
        == "speckit.plan"
    )


# ---------------------------------------------------------------------------
# render_body must not KeyError when title is missing
# ---------------------------------------------------------------------------
def test_render_body_missing_title_falls_back_to_node_id():
    node = {"came_from": ["somewhere"], "soft": ["(none)"]}
    body = render_body("pre", node, "my-node-id")
    assert body.startswith("# my-node-id"), body[:40]


def test_render_body_missing_title_and_no_node_id():
    node = {"going_to": ["next"]}
    body = render_body("post", node)
    assert body.startswith("# "), body[:40]


def test_render_body_uses_title_when_present():
    node = {"title": "/speckit.plan", "going_to": ["next"]}
    body = render_body("post", node, "plan")
    assert body.startswith("# /speckit.plan"), body[:40]


# ---------------------------------------------------------------------------
# Agent spawn gate: PreToolUse:Agent payloads
# ---------------------------------------------------------------------------
def test_resolve_command_agent_type_extracted():
    result = _resolve_command(
        "PreToolUse",
        {"tool_input": {"agentType": "speckit-verify", "agent_type": None}},
    )
    assert result == "agent:speckit-verify"


# ---------------------------------------------------------------------------
# End-to-end: dispatch() over stdin with adversarial payloads exits 0
# ---------------------------------------------------------------------------
def _run_dispatch(monkeypatch, payload, phase="pre", nodes_path=None):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    rc = dispatch(phase, nodes_path)
    return rc, out.getvalue()


def test_dispatch_nonstring_command_name_is_silent_noop(monkeypatch, tmp_path):
    nodes = tmp_path / "nodes.json"
    nodes.write_text(
        json.dumps({"plan": {"pre": {"title": "/speckit.plan", "soft": []}}})
    )
    rc, output = _run_dispatch(
        monkeypatch,
        {"hook_event_name": "UserPromptExpansion", "command_name": {"x": 1}},
        nodes_path=str(nodes),
    )
    assert rc == 0
    assert output == ""


def test_dispatch_nondict_tool_input_is_silent_noop(monkeypatch, tmp_path):
    nodes = tmp_path / "nodes.json"
    nodes.write_text(
        json.dumps({"plan": {"pre": {"title": "/speckit.plan", "soft": []}}})
    )
    rc, output = _run_dispatch(
        monkeypatch,
        {"hook_event_name": "PreToolUse", "tool_input": "bare-string"},
        nodes_path=str(nodes),
    )
    assert rc == 0
    assert output == ""


def test_dispatch_node_missing_title_does_not_crash(monkeypatch, tmp_path):
    nodes = tmp_path / "nodes.json"
    nodes.write_text(json.dumps({"plan": {"post": {"going_to": ["next"]}}}))
    rc, output = _run_dispatch(
        monkeypatch,
        {
            "hook_event_name": "PostToolUse",
            "tool_input": {"skill": "speckit-plan"},
        },
        phase="post",
        nodes_path=str(nodes),
    )
    assert rc == 0
    decision = json.loads(output)
    ctx = decision["hookSpecificOutput"]["additionalContext"]
    assert ctx.startswith("# plan"), ctx[:40]


def test_dispatch_malformed_stdin_is_silent_noop(monkeypatch, tmp_path):
    nodes = tmp_path / "nodes.json"
    nodes.write_text(
        json.dumps({"plan": {"pre": {"title": "/speckit.plan", "soft": []}}})
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO("{not valid json"))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    rc = dispatch("pre", str(nodes))
    assert rc == 0
    assert out.getvalue() == ""


def test_dispatch_unknown_event_is_silent_noop(monkeypatch, tmp_path):
    nodes = tmp_path / "nodes.json"
    nodes.write_text(
        json.dumps({"plan": {"pre": {"title": "/speckit.plan", "soft": []}}})
    )
    rc, output = _run_dispatch(
        monkeypatch,
        {"hook_event_name": "SomeOtherEvent", "command_name": "speckit.plan"},
        nodes_path=str(nodes),
    )
    assert rc == 0
    assert output == ""


def test_dispatch_missing_nodes_json_is_silent_noop(monkeypatch, tmp_path):
    rc, output = _run_dispatch(
        monkeypatch,
        {"hook_event_name": "UserPromptExpansion", "command_name": "speckit.plan"},
        nodes_path=str(tmp_path / "nonexistent.json"),
    )
    assert rc == 0
    assert output == ""
