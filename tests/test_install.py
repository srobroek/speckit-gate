"""Tests for install wiring: adapter loading, settings.json merge, cmd substitution."""

from __future__ import annotations

import json
import os

import pytest

from speckit_gate.cli import (
    _load_adapter_hooks,
    _resolve_gate_cmd,
    _substitute_cmd,
    _install_claude,
    _install_codex,
)


# ---------------------------------------------------------------------------
# importlib.resources adapter loading
# ---------------------------------------------------------------------------

def test_load_adapter_hooks_claude_returns_dict():
    data = _load_adapter_hooks("claude")
    assert isinstance(data, dict), "Claude adapter should load as dict"
    assert "hooks" in data, "Claude adapter must have 'hooks' key"


def test_load_adapter_hooks_codex_returns_dict():
    data = _load_adapter_hooks("codex")
    assert isinstance(data, dict), "Codex adapter should load as dict"
    assert "hooks" in data, "Codex adapter must have 'hooks' key"


def test_load_adapter_hooks_unknown_returns_none():
    result = _load_adapter_hooks("nonexistent_harness_xyz")
    assert result is None


def test_claude_adapter_has_no_UserPromptSubmit():
    """UserPromptSubmit fires on every prompt — too broad; UserPromptExpansion is correct."""
    data = _load_adapter_hooks("claude")
    assert "UserPromptSubmit" not in data["hooks"], (
        "Claude adapter must use UserPromptExpansion, not UserPromptSubmit"
    )


def test_claude_adapter_has_UserPromptExpansion():
    """UserPromptExpansion fires only on speckit.* command expansions — precise gate."""
    data = _load_adapter_hooks("claude")
    assert "UserPromptExpansion" in data["hooks"]


def test_adapter_hooks_contain_template_placeholder():
    """All command strings in both adapters must use the template placeholder."""
    for harness in ("claude", "codex"):
        data = _load_adapter_hooks(harness)
        raw = json.dumps(data)
        assert "{SPECKIT_GATE_CMD}" in raw, (
            f"{harness} adapter commands must contain {{SPECKIT_GATE_CMD}} placeholder"
        )
        assert "uvx speckit-gate" not in raw, (
            f"{harness} adapter must not hard-code 'uvx speckit-gate'"
        )


# ---------------------------------------------------------------------------
# Command resolution and substitution
# ---------------------------------------------------------------------------

def test_resolve_gate_cmd_from_source_checkout():
    """When pyproject.toml is present at repo root, should prefer uv run --project."""
    cmd = _resolve_gate_cmd()
    # In source checkout the pyproject.toml exists
    assert "speckit-gate" in cmd


def test_substitute_cmd_replaces_placeholder():
    data = {"hooks": {"X": [{"command": "{SPECKIT_GATE_CMD} dispatch pre"}]}}
    result = _substitute_cmd(data, "my-gate-cmd")
    assert result["hooks"]["X"][0]["command"] == "my-gate-cmd dispatch pre"


def test_substitute_cmd_does_not_mutate_input():
    data = {"hooks": {"X": [{"command": "{SPECKIT_GATE_CMD} dispatch pre"}]}}
    original_raw = json.dumps(data)
    _substitute_cmd(data, "x")
    assert json.dumps(data) == original_raw


# ---------------------------------------------------------------------------
# _install_claude: settings.json merge
# ---------------------------------------------------------------------------

def test_install_claude_creates_settings_json_fresh(tmp_path):
    """Fresh directory — settings.json should be created with hooks."""
    _install_claude(str(tmp_path), "speckit-gate")
    settings_path = tmp_path / ".claude" / "settings.json"
    assert settings_path.exists()
    settings = json.loads(settings_path.read_text())
    assert "hooks" in settings
    assert "UserPromptExpansion" in settings["hooks"]


def test_install_claude_does_not_write_hooks_json(tmp_path):
    """Must not write .claude/hooks.json — that file is not read by Claude Code."""
    _install_claude(str(tmp_path), "speckit-gate")
    assert not (tmp_path / ".claude" / "hooks.json").exists()


def test_install_claude_cmd_substituted(tmp_path):
    """The installed command must not contain the raw placeholder."""
    _install_claude(str(tmp_path), "my-speckit-gate-cmd")
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    raw = json.dumps(settings)
    assert "{SPECKIT_GATE_CMD}" not in raw
    assert "my-speckit-gate-cmd" in raw


def test_install_claude_merges_into_existing_settings(tmp_path):
    """Existing settings (other keys + existing hooks) are preserved."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    existing = {
        "theme": "dark",
        "hooks": {
            "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo hi"}]}],
        },
    }
    settings_path = claude_dir / "settings.json"
    settings_path.write_text(json.dumps(existing))

    _install_claude(str(tmp_path), "speckit-gate")

    settings = json.loads(settings_path.read_text())
    # Existing non-hook key preserved
    assert settings.get("theme") == "dark"
    # Existing PreToolUse entry preserved
    pre = settings["hooks"]["PreToolUse"]
    assert any(
        e.get("matcher") == "Bash" for e in pre
    ), "Existing PreToolUse:Bash entry must be preserved"
    # New entries added
    assert "UserPromptExpansion" in settings["hooks"]


def test_install_claude_no_duplicate_on_second_install(tmp_path):
    """Running install twice must not duplicate hook entries."""
    _install_claude(str(tmp_path), "speckit-gate")
    settings_before = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    _install_claude(str(tmp_path), "speckit-gate")
    settings_after = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert settings_before == settings_after


def test_install_claude_tolerates_corrupt_existing_settings(tmp_path):
    """A corrupt settings.json should be overwritten rather than crashing."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text("{not valid json!!!")

    # Should not raise
    _install_claude(str(tmp_path), "speckit-gate")
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert "hooks" in settings


# ---------------------------------------------------------------------------
# _install_codex: still writes .codex/hooks.json
# ---------------------------------------------------------------------------

def test_install_codex_writes_hooks_json(tmp_path):
    _install_codex(str(tmp_path), "speckit-gate")
    hooks_path = tmp_path / ".codex" / "hooks.json"
    assert hooks_path.exists()
    data = json.loads(hooks_path.read_text())
    assert "hooks" in data


def test_install_codex_cmd_substituted(tmp_path):
    _install_codex(str(tmp_path), "my-gate")
    data = json.loads((tmp_path / ".codex" / "hooks.json").read_text())
    raw = json.dumps(data)
    assert "{SPECKIT_GATE_CMD}" not in raw
    assert "my-gate" in raw
