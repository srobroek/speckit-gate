"""Tests for the deny path through the Claude adapter.

Verifies that an out-of-order event (running /speckit.plan before /speckit.specify
produces a spec.md artefact) is denied with the correct JSON shape.
"""

from __future__ import annotations

import io
import json
import os
import sys

import pytest

from speckit_gate.dispatch import dispatch
from speckit_gate.compile import compile_gates


FIXTURE_GATES = os.path.join(
    os.path.dirname(__file__), "fixtures", "gates.yaml"
)


def _make_nodes_json(tmp_path) -> str:
    """Compile fixture gates.yaml into a temp nodes.json and return the path."""
    nodes, cfg, _ = compile_gates(FIXTURE_GATES)
    output = {"_config": cfg, **nodes}
    p = tmp_path / "nodes.json"
    p.write_text(json.dumps(output, indent=2))
    return str(p)


def _dispatch_payload(monkeypatch, payload, phase, nodes_path):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    rc = dispatch(phase, nodes_path)
    return rc, out.getvalue()


# ---------------------------------------------------------------------------
# UserPromptExpansion deny: /speckit.plan before spec.md exists
# ---------------------------------------------------------------------------
def test_plan_before_spec_md_is_denied_prompt_expansion(monkeypatch, tmp_path):
    nodes_path = _make_nodes_json(tmp_path)
    # No spec.md in tmp_path → plan should be denied
    rc, output = _dispatch_payload(
        monkeypatch,
        {
            "hook_event_name": "UserPromptExpansion",
            "command_name": "speckit.plan",
            "cwd": str(tmp_path),
        },
        phase="pre",
        nodes_path=nodes_path,
    )
    assert rc == 0
    assert output, "expected a decision to be emitted"
    decision = json.loads(output)
    assert decision.get("decision") == "block", (
        f"expected block decision, got: {decision}"
    )
    assert "reason" in decision


# ---------------------------------------------------------------------------
# PreToolUse Skill deny: same scenario via Skill tool
# ---------------------------------------------------------------------------
def test_plan_before_spec_md_is_denied_pretooluse_skill(monkeypatch, tmp_path):
    nodes_path = _make_nodes_json(tmp_path)
    rc, output = _dispatch_payload(
        monkeypatch,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Skill",
            "tool_input": {"skill": "speckit-plan"},
            "cwd": str(tmp_path),
        },
        phase="pre",
        nodes_path=nodes_path,
    )
    assert rc == 0
    assert output
    decision = json.loads(output)
    hook_out = decision.get("hookSpecificOutput", {})
    assert hook_out.get("permissionDecision") == "deny", (
        f"expected deny, got: {hook_out}"
    )
    assert hook_out.get("permissionDecisionReason")


# ---------------------------------------------------------------------------
# Deprecated command always blocked
# ---------------------------------------------------------------------------
def test_deprecated_implement_is_always_blocked(monkeypatch, tmp_path):
    nodes_path = _make_nodes_json(tmp_path)
    # Even with all artefacts present, deprecated = always block
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "001-demo").mkdir()
    (tmp_path / "specs" / "001-demo" / "tasks.md").write_text("tasks")
    rc, output = _dispatch_payload(
        monkeypatch,
        {
            "hook_event_name": "UserPromptExpansion",
            "command_name": "speckit.implement",
            "cwd": str(tmp_path),
        },
        phase="pre",
        nodes_path=nodes_path,
    )
    assert rc == 0
    decision = json.loads(output)
    assert decision.get("decision") == "block"
    assert "deprecated" in decision.get("reason", "").lower()


# ---------------------------------------------------------------------------
# Post phase: advisory injection (no block)
# ---------------------------------------------------------------------------
def test_post_phase_emits_advisory_context(monkeypatch, tmp_path):
    nodes_path = _make_nodes_json(tmp_path)
    rc, output = _dispatch_payload(
        monkeypatch,
        {
            "hook_event_name": "PostToolUse",
            "tool_input": {"skill": "speckit-specify"},
            "cwd": str(tmp_path),
        },
        phase="post",
        nodes_path=nodes_path,
    )
    assert rc == 0
    if output:  # specify has a post node
        decision = json.loads(output)
        assert "hookSpecificOutput" in decision
        assert "additionalContext" in decision["hookSpecificOutput"]


# ---------------------------------------------------------------------------
# Happy path: plan runs fine when spec.md exists
# ---------------------------------------------------------------------------
def test_plan_allowed_when_spec_md_present(monkeypatch, tmp_path):
    nodes_path = _make_nodes_json(tmp_path)
    # Create spec.md so plan's hard_missing is satisfied
    specs_dir = tmp_path / "specs" / "001-demo"
    specs_dir.mkdir(parents=True)
    (specs_dir / "spec.md").write_text("# spec")
    # Write feature.json so feat resolves
    specify_dir = tmp_path / ".specify"
    specify_dir.mkdir()
    (specify_dir / "feature.json").write_text(
        json.dumps({"feature_directory": "specs/001-demo"})
    )
    rc, output = _dispatch_payload(
        monkeypatch,
        {
            "hook_event_name": "UserPromptExpansion",
            "command_name": "speckit.plan",
            "cwd": str(tmp_path),
        },
        phase="pre",
        nodes_path=nodes_path,
    )
    assert rc == 0
    if output:
        decision = json.loads(output)
        # Must NOT be a block decision
        assert decision.get("decision") != "block", (
            f"plan should not be blocked when spec.md exists: {decision}"
        )
