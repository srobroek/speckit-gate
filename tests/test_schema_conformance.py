"""Schema conformance tests for gates.yaml files.

Validates that the core preset and fixture gates.yaml conform to
schemas/gates.schema.json.  Stdlib-only: schema validation is done
manually against the JSON schema structure rather than via jsonschema
(no runtime dep).
"""

from __future__ import annotations

import json
import os

import pytest

from speckit_gate._yaml import load_yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(REPO_ROOT, "schemas", "gates.schema.json")
CORE_PRESET = os.path.join(REPO_ROOT, "presets", "core.gates.yaml")
FIXTURE_GATES = os.path.join(REPO_ROOT, "tests", "fixtures", "gates.yaml")


def _load_schema():
    with open(SCHEMA_PATH) as fh:
        return json.load(fh)


def _load_gates_yaml(path):
    with open(path) as fh:
        return load_yaml(fh.read())


def _validate_gate_entry(cmd, gate, errors):
    """Validate a single gate entry against the schema's gate definition."""
    if not isinstance(gate, dict):
        errors.append(f"gates.{cmd}: must be a mapping, got {type(gate)}")
        return

    # requires / produces: list of strings
    for field in ("requires", "produces"):
        val = gate.get(field)
        if val is not None:
            if not isinstance(val, list):
                errors.append(f"gates.{cmd}.{field}: must be a list, got {type(val)}")
            else:
                for i, item in enumerate(val):
                    if not isinstance(item, str):
                        errors.append(
                            f"gates.{cmd}.{field}[{i}]: must be string, got {type(item)}"
                        )

    # deprecated / spawn_agent: boolean
    for field in ("deprecated", "spawn_agent"):
        val = gate.get(field)
        if val is not None and not isinstance(val, bool):
            errors.append(f"gates.{cmd}.{field}: must be boolean, got {type(val)}")

    # context: string
    ctx = gate.get("context")
    if ctx is not None and not isinstance(ctx, str):
        errors.append(f"gates.{cmd}.context: must be string, got {type(ctx)}")

    # no extra keys beyond schema-defined properties
    allowed = {"requires", "produces", "deprecated", "spawn_agent", "context"}
    extra = set(gate.keys()) - allowed
    if extra:
        errors.append(f"gates.{cmd}: unexpected keys: {sorted(extra)}")


def _validate_config(cfg, errors):
    if cfg is None:
        return
    if not isinstance(cfg, dict):
        errors.append(f"config: must be a mapping, got {type(cfg)}")
        return
    allowed = {"prefix", "feature_root", "resolve", "messages"}
    extra = set(cfg.keys()) - allowed
    if extra:
        errors.append(f"config: unexpected keys: {sorted(extra)}")

    if "prefix" in cfg and not isinstance(cfg["prefix"], str):
        errors.append("config.prefix: must be string")
    if "feature_root" in cfg and not isinstance(cfg["feature_root"], str):
        errors.append("config.feature_root: must be string")
    if "resolve" in cfg:
        resolve = cfg["resolve"]
        if not isinstance(resolve, list):
            errors.append("config.resolve: must be a list")
        else:
            valid_strategies = {"git-branch", "newest-dir", "env-var", "feature-json"}
            for item in resolve:
                if not isinstance(item, str):
                    errors.append(f"config.resolve: items must be strings")
                elif item not in valid_strategies:
                    errors.append(
                        f"config.resolve: unknown strategy {item!r} "
                        f"(valid: {sorted(valid_strategies)})"
                    )
    if "messages" in cfg:
        msgs = cfg["messages"]
        if not isinstance(msgs, dict):
            errors.append("config.messages: must be a mapping")
        else:
            if "no_feature" in msgs and not isinstance(msgs["no_feature"], str):
                errors.append("config.messages.no_feature: must be string")


def _validate_document(doc):
    """Validate a parsed gates.yaml document. Returns list of error strings."""
    errors = []
    if not isinstance(doc, dict):
        errors.append("document: must be a top-level mapping")
        return errors

    allowed_top = {"config", "gates"}
    extra = set(doc.keys()) - allowed_top
    if extra:
        errors.append(f"document: unexpected top-level keys: {sorted(extra)}")

    if "gates" not in doc:
        errors.append("document: 'gates' key is required")
        return errors

    gates = doc["gates"]
    if not isinstance(gates, dict):
        errors.append("document.gates: must be a mapping")
        return errors
    if len(gates) == 0:
        errors.append("document.gates: must have at least one gate")

    for cmd, gate_def in gates.items():
        _validate_gate_entry(cmd, gate_def, errors)

    _validate_config(doc.get("config"), errors)
    return errors


# ---------------------------------------------------------------------------
# Conformance tests
# ---------------------------------------------------------------------------
def test_schema_file_exists():
    assert os.path.isfile(SCHEMA_PATH), f"gates.schema.json not found at {SCHEMA_PATH}"


def test_schema_is_valid_json():
    schema = _load_schema()
    assert isinstance(schema, dict)
    assert schema.get("type") == "object"
    assert "properties" in schema


def test_core_preset_conforms_to_schema():
    doc = _load_gates_yaml(CORE_PRESET)
    errors = _validate_document(doc)
    assert not errors, "core.gates.yaml schema violations:\n" + "\n".join(errors)


def test_fixture_gates_conforms_to_schema():
    doc = _load_gates_yaml(FIXTURE_GATES)
    errors = _validate_document(doc)
    assert not errors, "fixture gates.yaml schema violations:\n" + "\n".join(errors)


def test_minimal_valid_gates_yaml():
    """Minimal valid document: only 'gates' key with one entry."""
    doc = {"gates": {"specify": {"requires": [], "produces": []}}}
    errors = _validate_document(doc)
    assert not errors


def test_missing_gates_key_is_error():
    doc = {"config": {"prefix": "speckit."}}
    errors = _validate_document(doc)
    assert any("'gates'" in e or "gates" in e for e in errors)


def test_non_boolean_deprecated_is_error():
    doc = {"gates": {"cmd": {"requires": [], "produces": [], "deprecated": "yes"}}}
    errors = _validate_document(doc)
    assert any("deprecated" in e for e in errors)


def test_non_list_requires_is_error():
    doc = {"gates": {"cmd": {"requires": "single-string", "produces": []}}}
    errors = _validate_document(doc)
    assert any("requires" in e for e in errors)


def test_extra_top_level_key_is_error():
    doc = {"gates": {"cmd": {}}, "extra_key": "value"}
    errors = _validate_document(doc)
    assert any("extra_key" in e or "unexpected" in e for e in errors)
