# /speckit.gate.init

Initialise workflow gates for this project using speckit-gate.

## Steps

1. Run `uvx speckit-gate scan` to discover spec-kit commands in use.
2. Run `uvx speckit-gate propose` to show the default prerequisite table.
3. Confirm the table with the user (one question per unknown command).
4. Write the answers to a temporary JSON file.
5. Run `uvx speckit-gate init --answers <file>` to write gates.yaml.
6. Run `uvx speckit-gate compile` to compile gates.yaml → .specify/gates/nodes.json.

## Advisory enforcement

This extension provides advisory-only gates via context injection.
For deny-enforcement on Claude Code or Codex, install the native hook
adapters instead:

  uvx speckit-gate install --harness claude
  uvx speckit-gate install --harness codex

See https://github.com/srobroek/speckit-gate for the full install guide.
