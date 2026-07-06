---
name: speckit-gate
description: >-
  Initialise or update speckit-gate workflow gates for the current
  spec-kit project. Triggers on "gate", "gates.yaml", "init gates",
  "set up gates", "gate prerequisites", "speckit-gate".
---

# speckit-gate

TRIGGER
+ user says "init gates", "set up gates", "gates.yaml", "gate prerequisites"
+ user says "speckit-gate" or asks about workflow enforcement
- already have a complete gates.yaml → use `speckit-gate compile --check` instead

## Workflow

1. Run `uvx speckit-gate scan --root .` → collect command list
2. Run `uvx speckit-gate propose --root .` → render proposal table
3. Show full table to user: columns Command | Requires | Produces | Notes
   DEFAULT fills known commands from built-in map; unknown commands listed separately
4. Single confirm: "Does this look right? I'll ask about each unknown command."
5. For EACH unknown command in order — one question per turn:
   "What must exist before `<cmd>` runs? (artefacts or prior commands)"
   Record answer. Ask produces next if non-obvious.
6. Write answers to `/tmp/speckit-gate-answers.json` in shape:
   `{"commands": {"<cmd>": {"requires": [...], "produces": [...], "context": "..."}}}`
7. Run `uvx speckit-gate init --answers /tmp/speckit-gate-answers.json --root .`
8. Run `uvx speckit-gate compile --root .` → confirm gate count printed
9. Report: gates written, compile count, any spawn_agent warnings

Re-run path: if gates.yaml already exists, rescan, diff against current,
offer update only for changed commands.

## Rules

MUST show the full proposal table before asking any questions
MUST ask only one question per unknown command per turn
MUST NOT overwrite an existing gates.yaml without user confirmation
NOT for non-spec-kit project workflows → no trigger

OUTPUT
L1 `<N> gates compiled to .specify/gates/nodes.json`
   spawn_agent warnings — only if present
