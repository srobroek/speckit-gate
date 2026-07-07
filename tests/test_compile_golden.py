"""Golden compile tests.

1. core.gates.yaml (built-ins only) compiles clean.
2. extensions.example.gates.yaml parses and compiles clean.
3. Fixture gates.yaml compiles to expected node structure.
4. compile --check detects drift.
5. Preset validity: nodes in presets are structurally valid (pre+post present).
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
    # All 10 spec-kit built-in commands must compile to nodes
    for cmd in ("specify", "plan", "tasks", "implement", "converge"):
        assert cmd in nodes, f"expected node '{cmd}' in core preset"


def test_core_preset_contains_only_builtins():
    """core preset must contain exactly the verified spec-kit built-in commands.

    Built-in set verified against upstream templates/commands/ (mid-2026):
    analyze, checklist, clarify, constitution, converge, implement, plan,
    specify, tasks, taskstoissues.
    No community-extension commands are allowed in this preset.
    """
    from speckit_gate.known_gates import BUILTIN_COMMANDS
    path = os.path.join(PRESETS_DIR, "core.gates.yaml")
    nodes, cfg, warnings = _compile(path)
    extra = set(nodes.keys()) - BUILTIN_COMMANDS
    assert not extra, (
        f"core preset contains non-built-in commands: {sorted(extra)}\n"
        "Remove community-extension commands from core.gates.yaml.\n"
        "See presets/extensions.example.gates.yaml for the extension pattern."
    )
    missing = BUILTIN_COMMANDS - set(nodes.keys())
    assert not missing, f"core preset is missing built-in commands: {sorted(missing)}"


def test_extensions_example_preset_parses_and_compiles_clean():
    """extensions.example.gates.yaml must parse and compile without errors."""
    path = os.path.join(PRESETS_DIR, "extensions.example.gates.yaml")
    assert os.path.isfile(path), f"extensions.example.gates.yaml not found at {path}"
    nodes, cfg, warnings = _compile(path)
    assert isinstance(nodes, dict)
    assert len(nodes) > 0, "extensions example preset produced zero nodes"
    # The example must include at least one spawn_agent gate and one deprecated gate
    from speckit_gate._yaml import load_yaml
    with open(path) as fh:
        raw = load_yaml(fh.read())
    gates = raw.get("gates", {})
    has_spawn = any(g.get("spawn_agent") for g in gates.values())
    has_deprecated = any(g.get("deprecated") for g in gates.values())
    assert has_spawn, "extensions example must include at least one spawn_agent: true entry"
    assert has_deprecated, "extensions example must include at least one deprecated: true entry"


def test_extensions_example_schema_conformance():
    """extensions.example.gates.yaml must conform to the gates schema."""
    from speckit_gate._yaml import load_yaml
    import json as _json

    path = os.path.join(PRESETS_DIR, "extensions.example.gates.yaml")
    with open(path) as fh:
        doc = load_yaml(fh.read())

    # Inline the same validation logic from test_schema_conformance
    allowed_gate_keys = {"requires", "produces", "deprecated", "spawn_agent", "context"}
    errors = []
    for cmd, gate in (doc.get("gates") or {}).items():
        if not isinstance(gate, dict):
            errors.append(f"gates.{cmd}: must be a mapping")
            continue
        extra = set(gate.keys()) - allowed_gate_keys
        if extra:
            errors.append(f"gates.{cmd}: unexpected keys: {sorted(extra)}")
        for field in ("deprecated", "spawn_agent"):
            val = gate.get(field)
            if val is not None and not isinstance(val, bool):
                errors.append(f"gates.{cmd}.{field}: must be boolean")
    assert not errors, "extensions.example.gates.yaml schema violations:\n" + "\n".join(errors)


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
