"""Tests for directory-layout skill and extension discovery in scan.py.

Covers the A3 fix: skill directories are now resolved by name rather than
being opened as files (which caused IsADirectoryError).
"""

from __future__ import annotations

import os

import pytest

from speckit_gate.scan import (
    _command_from_skill_dir,
    _commands_from_extension_cmd_dir,
    scan_project,
)


# ---------------------------------------------------------------------------
# _command_from_skill_dir
# ---------------------------------------------------------------------------

class TestCommandFromSkillDir:
    def test_speckit_prefix_stripped(self, tmp_path):
        d = tmp_path / "speckit-plan"
        d.mkdir()
        assert _command_from_skill_dir(str(d)) == "plan"

    def test_compound_name(self, tmp_path):
        d = tmp_path / "speckit-security-review-branch"
        d.mkdir()
        assert _command_from_skill_dir(str(d)) == "security-review-branch"

    def test_skill_md_fallback(self, tmp_path):
        """Dir without speckit- prefix falls back to SKILL.md name: line."""
        d = tmp_path / "my-custom-skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: speckit-cleanup\ndescription: test\n---\n"
        )
        assert _command_from_skill_dir(str(d)) == "cleanup"

    def test_no_prefix_no_skill_md_returns_dir_name(self, tmp_path):
        """No speckit- prefix and no SKILL.md → returns None (cannot derive)."""
        d = tmp_path / "unrecognised"
        d.mkdir()
        assert _command_from_skill_dir(str(d)) is None

    def test_empty_dir_with_speckit_prefix(self, tmp_path):
        d = tmp_path / "speckit-analyze"
        d.mkdir()
        assert _command_from_skill_dir(str(d)) == "analyze"


# ---------------------------------------------------------------------------
# _commands_from_extension_cmd_dir
# ---------------------------------------------------------------------------

class TestCommandsFromExtensionCmdDir:
    def _make_cmds(self, tmp_path, ext_name: str, filenames: list[str]) -> list[str]:
        cmd_dir = tmp_path / ext_name / "commands"
        cmd_dir.mkdir(parents=True)
        for fn in filenames:
            (cmd_dir / fn).write_text("# placeholder")
        return _commands_from_extension_cmd_dir(ext_name, str(cmd_dir))

    def test_plain_same_name(self, tmp_path):
        """cleanup/commands/cleanup.md → cleanup"""
        cmds = self._make_cmds(tmp_path, "cleanup", ["cleanup.md"])
        assert cmds == ["cleanup"]

    def test_plain_subcommand(self, tmp_path):
        """critique/commands/run.md → critique-run"""
        cmds = self._make_cmds(tmp_path, "critique", ["run.md"])
        assert "critique-run" in cmds

    def test_plain_prefixed_subcommand(self, tmp_path):
        """security-review/commands/security-review-branch.md → security-review-branch"""
        cmds = self._make_cmds(
            tmp_path,
            "security-review",
            ["security-review.md", "security-review-branch.md"],
        )
        assert "security-review" in cmds
        assert "security-review-branch" in cmds

    def test_dotted_main_command(self, tmp_path):
        """tinyspec/commands/speckit.tinyspec.md → tinyspec-tinyspec (main cmd)"""
        cmds = self._make_cmds(
            tmp_path,
            "tinyspec",
            ["speckit.tinyspec.md"],
        )
        assert "tinyspec-tinyspec" in cmds

    def test_dotted_subcommand(self, tmp_path):
        """tinyspec/commands/speckit.tinyspec.implement.md → tinyspec-implement"""
        cmds = self._make_cmds(
            tmp_path,
            "tinyspec",
            ["speckit.tinyspec.implement.md", "speckit.tinyspec.classify.md"],
        )
        assert "tinyspec-implement" in cmds
        assert "tinyspec-classify" in cmds

    def test_dotted_roadmap(self, tmp_path):
        """roadmap/commands/speckit.roadmap.brief.md → roadmap-brief"""
        cmds = self._make_cmds(
            tmp_path,
            "roadmap",
            [
                "speckit.roadmap.brief.md",
                "speckit.roadmap.debrief.md",
                "speckit.roadmap.sync.md",
                "speckit.roadmap.write.md",
            ],
        )
        assert "roadmap-brief" in cmds
        assert "roadmap-debrief" in cmds
        assert "roadmap-sync" in cmds
        assert "roadmap-write" in cmds

    def test_template_files_skipped(self, tmp_path):
        """Files containing '-template' are skipped."""
        cmds = self._make_cmds(
            tmp_path,
            "critique",
            ["critique-template.md", "run.md"],
        )
        assert not any("template" in c for c in cmds)
        assert "critique-run" in cmds

    def test_non_md_files_ignored(self, tmp_path):
        cmd_dir = tmp_path / "cleanup" / "commands"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "cleanup.md").write_text("# cmd")
        (cmd_dir / "README.txt").write_text("ignore me")
        (cmd_dir / "config.yml").write_text("key: val")
        cmds = _commands_from_extension_cmd_dir("cleanup", str(cmd_dir))
        assert cmds == ["cleanup"]

    def test_agent_assign_subcommands(self, tmp_path):
        """agent-assign/commands/{assign,execute,validate}.md"""
        cmds = self._make_cmds(
            tmp_path,
            "agent-assign",
            ["assign.md", "execute.md", "validate.md"],
        )
        assert "agent-assign-assign" in cmds
        assert "agent-assign-execute" in cmds
        assert "agent-assign-validate" in cmds


# ---------------------------------------------------------------------------
# scan_project — fixture trees
# ---------------------------------------------------------------------------

class TestScanProjectDirLayout:
    def _make_skill_dirs(
        self,
        tmp_path,
        skill_names: list[str],
        write_skill_md: bool = True,
    ) -> None:
        base = tmp_path / ".claude" / "skills"
        base.mkdir(parents=True)
        for name in skill_names:
            d = base / name
            d.mkdir()
            if write_skill_md:
                (d / "SKILL.md").write_text(
                    f"---\nname: {name}\ndescription: test skill\n---\n"
                )

    def test_skill_dirs_discovered(self, tmp_path):
        self._make_skill_dirs(
            tmp_path,
            ["speckit-plan", "speckit-specify", "speckit-tasks"],
        )
        cmds = scan_project(str(tmp_path))
        assert "plan" in cmds
        assert "specify" in cmds
        assert "tasks" in cmds

    def test_skill_dirs_no_skill_md_still_discovered(self, tmp_path):
        """Directory name alone is sufficient — SKILL.md is optional."""
        self._make_skill_dirs(
            tmp_path,
            ["speckit-analyze", "speckit-implement"],
            write_skill_md=False,
        )
        cmds = scan_project(str(tmp_path))
        assert "analyze" in cmds
        assert "implement" in cmds

    def test_extension_commands_discovered(self, tmp_path):
        ext_base = tmp_path / ".specify" / "extensions"
        (ext_base / "cleanup" / "commands").mkdir(parents=True)
        (ext_base / "cleanup" / "commands" / "cleanup.md").write_text("# cmd")
        (ext_base / "critique" / "commands").mkdir(parents=True)
        (ext_base / "critique" / "commands" / "run.md").write_text("# cmd")
        (ext_base / "critique" / "commands" / "critique-template.md").write_text("# tmpl")

        cmds = scan_project(str(tmp_path))
        assert "cleanup" in cmds
        assert "critique-run" in cmds
        assert not any("template" in c for c in cmds)

    def test_skill_dirs_plus_extensions(self, tmp_path):
        """Mixed layout: skills + extensions both discovered."""
        self._make_skill_dirs(tmp_path, ["speckit-plan", "speckit-specify"])
        ext_base = tmp_path / ".specify" / "extensions"
        (ext_base / "roadmap" / "commands").mkdir(parents=True)
        for fn in ["speckit.roadmap.sync.md", "speckit.roadmap.write.md"]:
            (ext_base / "roadmap" / "commands" / fn).write_text("# cmd")

        cmds = scan_project(str(tmp_path))
        assert "plan" in cmds
        assert "specify" in cmds
        assert "roadmap-sync" in cmds
        assert "roadmap-write" in cmds

    def test_no_double_counting_flat_files(self, tmp_path):
        """Flat .md files in skills dir (non-dir layout) still extracted via content."""
        skills_dir = tmp_path / ".claude" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "my-skill.md").write_text(
            "Use /speckit.verify and /speckit.review-run."
        )
        cmds = scan_project(str(tmp_path))
        assert "verify" in cmds
        assert "review-run" in cmds

    def test_extensions_hidden_dirs_skipped(self, tmp_path):
        """Dotfile dirs like .cache inside extensions/ are ignored."""
        ext_base = tmp_path / ".specify" / "extensions"
        (ext_base / ".cache").mkdir(parents=True)
        (ext_base / ".registry").mkdir(parents=True)
        (ext_base / "cleanup" / "commands").mkdir(parents=True)
        (ext_base / "cleanup" / "commands" / "cleanup.md").write_text("# cmd")
        cmds = scan_project(str(tmp_path))
        assert "cleanup" in cmds

    def test_full_realistic_layout(self, tmp_path):
        """Simulates a project with 47 skill dirs + multi-extension commands."""
        skill_names = [
            "speckit-plan", "speckit-specify", "speckit-tasks", "speckit-analyze",
            "speckit-checklist", "speckit-clarify", "speckit-implement",
            "speckit-converge", "speckit-constitution",
            "speckit-cleanup", "speckit-cleanup-run",
            "speckit-critique-run",
            "speckit-iterate-apply", "speckit-iterate-define",
            "speckit-verify", "speckit-verify-tasks",
            "speckit-review-run", "speckit-review-code", "speckit-review-comments",
            "speckit-review-errors", "speckit-review-simplify", "speckit-review-tests",
            "speckit-review-types",
            "speckit-qa-run", "speckit-retro-run",
            "speckit-roadmap-brief", "speckit-roadmap-debrief",
            "speckit-roadmap-sync", "speckit-roadmap-write",
            "speckit-security-review-branch", "speckit-security-review-audit",
            "speckit-security-review-init", "speckit-security-review-plan",
            "speckit-security-review-staged", "speckit-security-review-tasks",
            "speckit-security-review-followup", "speckit-security-review-apply",
            "speckit-security-review-export",
            "speckit-taskstoissues",
            "speckit-agent-assign-assign", "speckit-agent-assign-execute",
            "speckit-agent-assign-validate", "speckit-agent-context-update",
            "speckit-fix-findings", "speckit-fix-findings-run",
            "speckit-tinyspec-tinyspec", "speckit-tinyspec-implement",
            "speckit-tinyspec-classify",
            "speckit-status-report-show",
        ]
        self._make_skill_dirs(tmp_path, skill_names)

        # Also add some extension command dirs
        ext_base = tmp_path / ".specify" / "extensions"
        (ext_base / ".cache").mkdir(parents=True)
        (ext_base / "tinyspec" / "commands").mkdir(parents=True)
        for fn in ["speckit.tinyspec.md", "speckit.tinyspec.implement.md",
                   "speckit.tinyspec.classify.md"]:
            (ext_base / "tinyspec" / "commands" / fn).write_text("# cmd")

        cmds = scan_project(str(tmp_path))
        # Skills
        assert "plan" in cmds
        assert "security-review-audit" in cmds
        assert "tinyspec-tinyspec" in cmds
        assert "status-report-show" in cmds
        # Extensions (should not double-add)
        assert "tinyspec-implement" in cmds
        assert "tinyspec-classify" in cmds
        # No template, no hidden dirs
        assert not any("template" in c for c in cmds)
        # At least the skill count worth of commands
        assert len(cmds) >= len(skill_names)
