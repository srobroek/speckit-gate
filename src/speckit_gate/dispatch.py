"""Hook dispatcher — the runtime engine.

Reads .specify/gates/nodes.json (compiled from gates.yaml), resolves the
current command from the hook event payload, evaluates hard rules, and
emits a JSON response to stdout.

Config header in nodes.json drives all product-specific behavior:
  - command prefix matching
  - feature_root for artefact path resolution
  - block/advisory messages

Design:
  - stdlib-only runtime deps
  - exits 0 always (hook errors must not block user workflow)
  - graceful on malformed payloads (port of robustness tests)
  - deny = same JSON shapes as the reference dispatcher
"""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
from typing import Any

from speckit_gate.resolve import as_str, resolve_project_root, resolve_feature, path_present


# ---------------------------------------------------------------------------
# Nodes.json location
# ---------------------------------------------------------------------------
def _find_nodes_json(proj_root: str) -> str:
    return os.path.join(proj_root, ".specify", "gates", "nodes.json")


def _load_nodes(nodes_path: str) -> tuple[dict, dict]:
    """Load nodes.json; returns (nodes, config).  Empty dicts on failure."""
    if not nodes_path or not os.path.isfile(nodes_path):
        return {}, {}
    try:
        with open(nodes_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}, {}
    if not isinstance(data, dict):
        return {}, {}
    cfg = data.get("_config") or {}
    nodes = {k: v for k, v in data.items() if k != "_config"}
    return nodes, cfg if isinstance(cfg, dict) else {}


# ---------------------------------------------------------------------------
# Command extraction (config-driven prefix)
# ---------------------------------------------------------------------------
def _parse_speckit_slash(text: str, prefix: str) -> str:
    """Find the first /<prefix>X token in text and return stripped form."""
    # Build pattern from prefix: e.g. "speckit." → r"/speckit\.[a-z][a-z0-9.\-]*"
    escaped = re.escape(prefix)
    pattern = r"/" + escaped + r"[a-z][a-z0-9.\-]*"
    match = re.search(pattern, text)
    if not match:
        return ""
    return match.group(0).lstrip("/")


def _resolve_command(event: str, payload: dict, prefix: str = "speckit.") -> str:
    """Extract command string from payload for various event types."""
    if event == "UserPromptExpansion":
        return as_str(payload.get("command_name"))
    if event in ("PreToolUse", "PostToolUse"):
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            tool_input = {}
        # Check for agent-type spawn events
        agent_type = as_str(tool_input.get("agent_type") or tool_input.get("agentType"))
        if agent_type:
            return "agent:" + agent_type
        cmd = as_str(tool_input.get("skill")) or as_str(tool_input.get("command_name"))
        if cmd:
            return cmd
        return _parse_speckit_slash(as_str(tool_input.get("prompt")), prefix)
    if event == "UserPromptSubmit":
        return _parse_speckit_slash(as_str(payload.get("prompt")), prefix)
    return ""


def _normalize(cmd: str, prefix: str = "speckit.") -> str:
    """Strip prefix, convert dots to hyphens for node key lookup."""
    raw = cmd
    prefix_dotted = prefix.rstrip(".")
    prefix_hyphen = prefix_dotted.replace(".", "-") + "-"
    prefix_dot = prefix_dotted + "."
    if raw.startswith(prefix_hyphen):
        raw = raw[len(prefix_hyphen):]
    elif raw.startswith(prefix_dot):
        raw = raw[len(prefix_dot):]
    elif raw.startswith(prefix_dotted + "-"):
        raw = raw[len(prefix_dotted + "-"):]
    if not raw:
        return ""
    return raw.replace(".", "-")


def _resolve_node_id(node_id: str, nodes: dict) -> str:
    """Exact match first; then strip trailing segments until a node matches."""
    if node_id in nodes:
        return node_id
    parts = node_id.split("-")
    while len(parts) > 1:
        parts.pop()
        candidate = "-".join(parts)
        if candidate in nodes:
            return candidate
    return ""


# ---------------------------------------------------------------------------
# Hard-rule evaluation
# ---------------------------------------------------------------------------
def _subst(tmpl: str, feat: str) -> str:
    return tmpl.replace("<feat>", feat)


def _resolve_path(tmpl: str, feat: str, proj_root: str, feature_root: str) -> str:
    path = _subst(tmpl, feat)
    # Replace 'specs/' with configured feature_root if different
    if feature_root != "specs" and path.startswith("specs/"):
        path = feature_root + "/" + path[6:]
    if not os.path.isabs(path):
        path = os.path.join(proj_root, path)
    return path


def _evaluate_block(
    node: dict,
    feat: str,
    proj_root: str,
    feature_root: str,
    no_feature_msg: str,
) -> str:
    """Return block reason string or '' if nothing blocks."""
    for reason in node.get("hard_deprecated", []):
        return reason
    for tmpl in node.get("hard_missing", []):
        if "<feat>" in tmpl and not feat:
            return no_feature_msg
        path = _resolve_path(tmpl, feat, proj_root, feature_root)
        if not path_present(path):
            return "Required artefact missing: " + path
    for tmpl in node.get("hard_exists", []):
        if "<feat>" in tmpl and not feat:
            continue
        path = _resolve_path(tmpl, feat, proj_root, feature_root)
        if path_present(path):
            return (
                "Conflicting artefact present: "
                + path
                + " — use the refine/update flow to amend instead of re-running"
            )
    return ""


# ---------------------------------------------------------------------------
# Body rendering (ported from reference dispatcher)
# ---------------------------------------------------------------------------
def _render_section(heading: str, bullets: list[str]) -> str:
    lines = ["## " + heading]
    for b in bullets:
        lines.append("- " + b)
    return "\n".join(lines)


def render_body(phase: str, node: dict, node_id: str = "") -> str:
    parts = ["# " + node.get("title", node_id)]
    if phase == "pre":
        if "came_from" in node:
            parts.append(_render_section("Came from", node["came_from"]))
        precond: list[str] = []
        for tmpl in node.get("hard_missing", []):
            precond.append("HARD-MISSING: " + tmpl)
        for tmpl in node.get("hard_exists", []):
            precond.append("HARD-EXISTS: " + tmpl)
        for tmpl in node.get("hard_deprecated", []):
            precond.append("HARD-DEPRECATED: " + tmpl)
        for s in node.get("soft", []):
            if s.startswith("(") or s == "(none)":
                precond.append(s)
            else:
                precond.append("SOFT: " + s)
        if "soft" in node:
            parts.append(_render_section("Preconditions", precond))
        if "context" in node:
            parts.append(_render_section("Context", node["context"]))
    else:
        if "going_to" in node:
            parts.append(_render_section("Going to", node["going_to"]))
        if "postconditions" in node:
            parts.append(_render_section("Postconditions", node["postconditions"]))
        if "context" in node:
            parts.append(_render_section("Context", node["context"]))
        if "conditional" in node:
            parts.append(_render_section("Conditional branching", node["conditional"]))
    return "\n\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Main dispatch loop
# ---------------------------------------------------------------------------
def dispatch(phase: str, nodes_path: str | None = None) -> int:
    """Read JSON payload from stdin, emit hook response to stdout.
    Returns 0 always.
    """
    payload_text = sys.stdin.read()
    try:
        payload = json.loads(payload_text) if payload_text.strip() else {}
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0

    event = as_str(payload.get("hook_event_name"))
    if event not in ("UserPromptExpansion", "PreToolUse", "PostToolUse", "UserPromptSubmit"):
        return 0

    proj_root = resolve_project_root(payload)

    # Load nodes from the given path or the project default
    if nodes_path is None:
        nodes_path = _find_nodes_json(proj_root)
    nodes, cfg = _load_nodes(nodes_path)
    if not nodes:
        return 0  # no gates configured → silent pass-through

    prefix = cfg.get("prefix", "speckit.")
    feature_root = cfg.get("feature_root", "specs")
    no_feature_msg = (
        cfg.get("messages", {}).get("no_feature")
        or "No active spec-kit feature resolved — run the specify step first"
    )

    cmd = _resolve_command(event, payload, prefix)
    if not cmd:
        return 0

    node_id = _normalize(cmd, prefix)
    if not node_id:
        return 0

    node_id = _resolve_node_id(node_id, nodes)
    if not node_id:
        return 0

    node_entry = nodes.get(node_id)
    if not isinstance(node_entry, dict):
        return 0

    node = node_entry.get(phase)
    if not isinstance(node, dict):
        return 0

    node_body = render_body(phase, node, node_id)
    feat = resolve_feature(proj_root, feature_root)

    if phase == "pre":
        block_reason = _evaluate_block(node, feat, proj_root, feature_root, no_feature_msg)
        if block_reason:
            if event in ("UserPromptExpansion", "UserPromptSubmit"):
                out = {
                    "decision": "block",
                    "reason": block_reason,
                    "hookSpecificOutput": {
                        "hookEventName": event,
                        "additionalContext": node_body,
                    },
                }
            elif event == "PreToolUse":
                out = {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": block_reason,
                        "additionalContext": node_body,
                    },
                }
            else:
                out = {
                    "hookSpecificOutput": {
                        "hookEventName": event,
                        "additionalContext": node_body,
                    },
                }
            sys.stdout.write(json.dumps(out, indent=2) + "\n")
            return 0

    out = {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": node_body,
        },
    }
    sys.stdout.write(json.dumps(out, indent=2) + "\n")
    return 0
