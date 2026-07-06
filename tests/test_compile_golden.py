"""Golden compile tests.

1. Both presets (core.gates.yaml, srobroek-full.gates.yaml) compile clean.
2. Fixture gates.yaml compiles to expected node structure.
3. compile --check detects drift.
4. Preset validity: nodes in presets are structurally valid (pre+post present).
"""

from __future__ import annotations

import json
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRESETS_DIR = os.path.join(REPO_ROOT, "presets")
FIXTURE_GATES = os.path.join(REPO_ROOT, "tests", "fixtures", "gates.yaml")


def _compile(gates_yaml_path):
    from speckit_gate.compile import compile_gates
    return compile_gates(gates_yaml_path)


# ---------------------------------------------------------------------------
# Both presets compile clean (no exception, no errors)
# ---------------------------------------------------------------------------
def test_core_preset_compiles_clean():
    path = os.path.join(PRESETS_DIR, "core.gates.yaml")
    assert os.path.isfile(path), f"core.gates.yaml not found at {path}"
    nodes, cfg, warnings = _compile(path)
    assert isinstance(nodes, dict)
    assert len(nodes) > 0, "core preset produced zero nodes"
    # spawn_agent warnings are expected; no assertion errors
    for cmd in ("specify", "plan", "tasks", "verify", "verify-tasks"):
        assert cmd in nodes, f"expected node '{cmd}' in core preset"


def test_core_preset_has_expected_nodes():
    """core preset must cover all built-in spec-kit commands."""
    path = os.path.join(PRESETS_DIR, "core.gates.yaml")
    nodes, cfg, warnings = _compile(path)
    expected_nodes = {
        "specify", "clarify", "plan", "tasks", "checklist", "critique-run",
        "analyze", "taskstoissues", "checkpoint-commit",
        "agent-assign-assign", "agent-assign-validate", "agent-assign-execute",
        "implement", "converge",
        "verify-tasks", "verify", "review-run", "qa-run", "sync-conflicts", "archive",
        "refine-update", "refine-propagate",
        "iterate-define", "iterate-apply",
        "bugfix-verify", "bugfix-patch",
        "tinyspec-tinyspec", "tinyspec-implement",
        "fleet-review",
    }
    missing = expected_nodes - set(nodes.keys())
    assert not missing, f"core preset missing nodes: {sorted(missing)}"


def test_core_preset_spawn_agent_nodes():
    """verify, verify-tasks, and agent-assign-execute have spawn_agent: true."""
    from speckit_gate._yaml import load_yaml
    path = os.path.join(PRESETS_DIR, "core.gates.yaml")
    with open(path) as fh:
        raw = load_yaml(fh.read())
    gates = raw.get("gates", {})
    for cmd in ("verify", "verify-tasks", "agent-assign-execute"):
        assert gates.get(cmd, {}).get("spawn_agent") is True, (
            f"expected spawn_agent: true on '{cmd}' in core preset"
        )


# ---------------------------------------------------------------------------
# Fixture gates.yaml: structural checks
# ---------------------------------------------------------------------------
def test_fixture_compiles_to_expected_nodes():
    nodes, cfg, warnings = _compile(FIXTURE_GATES)
    assert "specify" in nodes
    assert "plan" in nodes
    assert "tasks" in nodes
    assert "verify" in nodes
    assert "implement" in nodes


def test_fixture_deprecated_node_has_hard_deprecated():
    nodes, cfg, warnings = _compile(FIXTURE_GATES)
    implement = nodes["implement"]
    pre = implement.get("pre", {})
    assert pre.get("hard_deprecated"), "deprecated node should have hard_deprecated"


def test_fixture_spawn_agent_warning_emitted():
    _, _, warnings = _compile(FIXTURE_GATES)
    assert any("spawn_agent" in w for w in warnings), (
        "expected spawn_agent compile warning for 'verify'"
    )


def test_fixture_pre_post_both_present():
    nodes, _, _ = _compile(FIXTURE_GATES)
    for cmd, entry in nodes.items():
        assert "pre" in entry, f"node '{cmd}' missing 'pre' phase"
        assert "post" in entry, f"node '{cmd}' missing 'post' phase"
        assert "title" in entry["pre"], f"node '{cmd}'.pre missing title"
        assert "title" in entry["post"], f"node '{cmd}'.post missing title"


# ---------------------------------------------------------------------------
# compile --check drift detection
# ---------------------------------------------------------------------------
def test_check_detects_drift(tmp_path):
    from speckit_gate.compile import compile_gates, check_drift

    nodes, cfg, _ = compile_gates(FIXTURE_GATES)
    output = {"_config": cfg, **nodes}

    # Write a tampered copy
    tampered = dict(output)
    first_key = [k for k in tampered if k != "_config"][0]
    tampered[first_key] = {"pre": {"title": "TAMPERED"}, "post": {"title": "TAMPERED"}}
    tampered_path = tmp_path / "nodes.json"
    tampered_path.write_text(json.dumps(tampered, indent=2))

    has_drift, diff = check_drift(output, str(tampered_path))
    assert has_drift, "expected drift to be detected"
    assert "DRIFT" in diff or diff, "expected diff text"


def test_check_no_drift_when_in_sync(tmp_path):
    from speckit_gate.compile import compile_gates, check_drift

    nodes, cfg, _ = compile_gates(FIXTURE_GATES)
    output = {"_config": cfg, **nodes}

    synced_path = tmp_path / "nodes.json"
    synced_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")

    has_drift, diff = check_drift(output, str(synced_path))
    assert not has_drift, "expected no drift when in sync"


def test_check_missing_file_reports_drift(tmp_path):
    from speckit_gate.compile import compile_gates, check_drift

    nodes, cfg, _ = compile_gates(FIXTURE_GATES)
    output = {"_config": cfg, **nodes}
    missing = str(tmp_path / "does-not-exist.json")

    has_drift, diff = check_drift(output, missing)
    assert has_drift
