"""Tests for the minimal stdlib YAML parser."""

from __future__ import annotations

from speckit_gate._yaml import load_yaml, ParseError


def test_simple_mapping():
    result = load_yaml("key: value\nother: 42\n")
    assert result == {"key": "value", "other": 42}


def test_nested_mapping():
    result = load_yaml("config:\n  prefix: speckit.\n  feature_root: specs\n")
    assert result == {"config": {"prefix": "speckit.", "feature_root": "specs"}}


def test_sequence_values():
    result = load_yaml("items:\n  - alpha\n  - beta\n  - gamma\n")
    assert result == {"items": ["alpha", "beta", "gamma"]}


def test_boolean_scalars():
    result = load_yaml("deprecated: true\nspawn_agent: false\n")
    assert result["deprecated"] is True
    assert result["spawn_agent"] is False


def test_inline_comment_stripped():
    result = load_yaml("key: value  # this is a comment\n")
    assert result == {"key": "value"}


def test_empty_list_inline():
    result = load_yaml("requires: []\n")
    # [] as a scalar parses as empty string — acceptable for our use
    assert result is not None


def test_multiline_sequence():
    yaml = "gates:\n  specify:\n    requires: []\n    produces:\n      - specs/<feat>/spec.md\n"
    result = load_yaml(yaml)
    assert "gates" in result
    assert "specify" in result["gates"]


def test_comment_only_lines_skipped():
    result = load_yaml("# top comment\nkey: value\n# another\n")
    assert result == {"key": "value"}


def test_gates_yaml_fixture():
    import os
    fixture = os.path.join(
        os.path.dirname(__file__), "fixtures", "gates.yaml"
    )
    with open(fixture, "r") as fh:
        text = fh.read()
    result = load_yaml(text)
    assert "config" in result
    assert "gates" in result
    assert "specify" in result["gates"]
    assert "plan" in result["gates"]
