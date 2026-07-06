"""Default prerequisite map for spec-kit core commands and common extensions.

These are the DEFAULTS shipped with speckit-gate.  A project's gates.yaml
overrides or extends this map.  Keys are command names in the dispatcher's
normalized form (hyphens, no 'speckit.' prefix).

Format:
    {cmd: {"requires": [cmd, ...], "produces": [artefact, ...], "context": str}}

The values here match the locked srobroek-full preset DAG (ported from the
28-node speckit-dag-hooks nodes.json).  Community extensions or new spec-kit
commands that are not listed here are treated as unknown by the scan/propose
step; the init interview asks about them individually.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Core spec-kit commands
# ---------------------------------------------------------------------------
KNOWN_GATES: dict[str, dict] = {
    # --- spec phase ---
    "specify": {
        "requires": [],
        "produces": ["specs/<feat>/spec.md"],
        "context": "Initial spec authoring; must precede all other phases.",
    },
    "clarify": {
        "requires": ["specify"],
        "produces": ["specs/<feat>/clarifications.md"],
        "context": "Resolves ambiguities left open in spec.md.",
    },
    "plan": {
        "requires": ["specify"],
        "produces": ["specs/<feat>/plan.md"],
        "context": "Decomposes spec into design and implementation plan.",
    },
    "tasks": {
        "requires": ["plan"],
        "produces": ["specs/<feat>/tasks.md"],
        "context": "Decomposes plan into discrete, testable tasks.",
    },
    "checklist": {
        "requires": ["specify", "plan", "tasks"],
        "produces": ["specs/<feat>/checklist.md"],
        "context": "Requirements-quality gate before implementation.",
    },
    "critique-run": {
        "requires": ["plan", "tasks"],
        "produces": ["specs/<feat>/critique-report.md"],
        "context": "Dual-lens review (product strategy + engineering risk).",
    },
    "analyze": {
        "requires": ["tasks"],
        "produces": ["specs/<feat>/analysis.md"],
        "context": "Surfaces risks, missing tasks, and over-broad tasks.",
    },
    "taskstoissues": {
        "requires": ["tasks"],
        "produces": ["gh issues", "specs/<feat>/issue-map.md"],
        "context": "Turns tasks into trackable GitHub issues.",
    },
    "checkpoint-commit": {
        "requires": ["specify"],
        "produces": ["git commit"],
        "context": "Locks in spec/plan/tasks before or after execution.",
    },
    # --- implementation phase ---
    "agent-assign-assign": {
        "requires": ["tasks"],
        "produces": ["specs/<feat>/agent-assignments.yml"],
        "context": "Matches tasks to specialised sub-agents.",
    },
    "agent-assign-validate": {
        "requires": ["agent-assign-assign"],
        "produces": [],
        "context": "Validates agent assignments are correct and agents exist.",
    },
    "agent-assign-execute": {
        "requires": ["agent-assign-assign", "agent-assign-validate"],
        "produces": ["code changes", "specs/<feat>/task-<n>.report.md"],
        "context": "Executes tasks via per-task sub-agents.",
        "spawn_agent": True,
    },
    "implement": {
        "requires": ["tasks"],
        "produces": [],
        "deprecated": True,
        "context": "Deprecated. Use agent-assign.assign/validate/execute.",
    },
    "converge": {
        "requires": ["specify", "plan", "tasks"],
        "produces": ["specs/<feat>/tasks.md"],
        "context": "Closes gap between spec intent and actual implementation.",
    },
    # --- post-impl phase ---
    "verify-tasks": {
        "requires": ["tasks"],
        "produces": ["specs/<feat>/verify-tasks-report.md"],
        "context": "Detects phantom completions in a fresh context.",
        "spawn_agent": True,
    },
    "verify": {
        "requires": ["plan"],
        "produces": ["specs/<feat>/verify-report.md"],
        "context": "Validates implementation against plan.",
        "spawn_agent": True,
    },
    "review-run": {
        "requires": ["verify"],
        "produces": ["specs/<feat>/review-report.md"],
        "context": "Orchestrates granular review sub-agents.",
    },
    "qa-run": {
        "requires": ["review-run"],
        "produces": ["specs/<feat>/qa-report.md"],
        "context": "Systematic QA: browser-driven or CLI-based acceptance.",
    },
    "sync-conflicts": {
        "requires": ["sync-report"],
        "produces": [],
        "context": "Surfaces contradictions between specs or shared contracts.",
    },
    "archive": {
        "requires": ["verify-report", "review-report"],
        "produces": ["specs/archived/<feat>/"],
        "context": "Terminal step; moves specs/<feat>/ to archived/.",
    },
    # --- refine loop ---
    "refine-update": {
        "requires": ["specify"],
        "produces": ["artefact updates"],
        "context": "Incremental edits to existing artefacts.",
    },
    "refine-propagate": {
        "requires": ["refine-diff"],
        "produces": ["downstream artefact updates"],
        "context": "Pushes spec diff into plan, tasks, and issues.",
    },
    # --- iterate loop ---
    "iterate-define": {
        "requires": ["specify"],
        "produces": ["specs/<feat>/pending-iteration.md"],
        "context": "Scope/intent pivots distinct from incremental refine.",
    },
    "iterate-apply": {
        "requires": ["iterate-define"],
        "produces": ["spec/plan/tasks updated"],
        "context": "Applies iteration intent to spec + plan + tasks.",
    },
    # --- bugfix sub-cycle ---
    "bugfix-verify": {
        "requires": ["bugfix-report"],
        "produces": [],
        "context": "Reproduces the bug with a failing test before patching.",
    },
    "bugfix-patch": {
        "requires": ["bugfix-verify"],
        "produces": [],
        "context": "Applies the fix; reruns the failing test to confirm.",
    },
    # --- tinyspec sub-cycle ---
    "tinyspec-tinyspec": {
        "requires": [],
        "produces": ["specs/<feat>/tinyspec.md"],
        "context": "Lightweight spec for small, self-contained changes.",
    },
    "tinyspec-implement": {
        "requires": ["tinyspec-tinyspec"],
        "produces": [],
        "context": "Implements a small change directly from its tinyspec.",
    },
    # --- fleet orchestration ---
    "fleet-review": {
        "requires": ["fleet-state"],
        "produces": [],
        "context": "Cross-model evaluation of plan.md and tasks.md.",
    },
}

# ---------------------------------------------------------------------------
# Common community extensions (advisory only; not hard-gated by default)
# ---------------------------------------------------------------------------
COMMUNITY_EXTENSION_GATES: dict[str, dict] = {
    "roadmap-write": {
        "requires": [],
        "produces": ["roadmap.md"],
        "context": "Creates or amends the project spec roadmap.",
    },
    "roadmap-sync": {
        "requires": ["roadmap-write"],
        "produces": [],
        "context": "Detects drift between roadmap and specs on disk.",
    },
    "security-review-branch": {
        "requires": ["tasks"],
        "produces": ["specs/<feat>/security-review.md"],
        "context": "Security risks introduced by the current branch.",
    },
    "memory-md-capture": {
        "requires": [],
        "produces": ["docs/memory/"],
        "context": "Captures durable lessons from completed work.",
    },
}
