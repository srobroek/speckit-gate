# speckit-gate

Harness-agnostic workflow gates for spec-kit projects.

Prevents out-of-order spec-kit command invocations by evaluating prerequisite
artefacts at hook time. Supports hard-deny enforcement on Claude Code and Codex;
advisory-only enforcement on all other spec-kit harnesses.

## Install

### Option 1 — uvx (one-shot, no install required)

```bash
# Scan and initialise gates in the current project
uvx speckit-gate init --defaults
uvx speckit-gate compile

# Install Claude Code hooks
uvx speckit-gate install --harness claude
```

### Option 2 — Claude Code plugin (persistent, recommended for Claude Code)

```bash
# From within Claude Code, or via the CLI:
claude plugin install srobroek/speckit-gate
```

The `.claude-plugin/plugin.json` in `adapters/claude/` wires
`UserPromptExpansion`, `PreToolUse:Skill`, and `PreToolUse:Agent` hooks.

### Option 3 — spec-kit bundle (all harnesses, advisory enforcement)

```bash
# Add the community bundle catalog and install
specify bundle catalog add https://github.com/srobroek/speckit-gate/releases/latest/download/bundles.json --id speckit-gate
specify bundle install speckit-gate
```

See [Bundle adapter rationale](#bundle-adapter) below.

### Option 4 — APM external source

```yaml
# In apm.yml:
dependencies:
  apm:
    - repo: srobroek/speckit-gate
      ref: ">=0.1.0"
```

```bash
apm install
```

## Quick start

```yaml
# gates.yaml — 10-line example
config:
  prefix: speckit.
  feature_root: specs
  resolve: [git-branch, newest-dir]

gates:
  plan:
    requires: [specify]
    produces: [specs/<feat>/plan.md]
    context: Decomposes spec into implementation plan.
  tasks:
    requires: [plan]
    produces: [specs/<feat>/tasks.md]
    context: Decomposes plan into discrete tasks.
```

Compile to nodes.json:

```bash
speckit-gate compile
# → Compiled 2 gates → .specify/gates/nodes.json
```

## Agent-driven interview

Use the `speckit-gate` skill (in `skills/speckit-gate/SKILL.md`) with
Claude Code or any skill-capable harness.  The skill:

1. Scans the project for spec-kit commands.
2. Shows a full proposal table (known prerequisites pre-filled).
3. Asks ONE question per unknown command.
4. Writes `gates.yaml` via `init --answers` and runs `compile`.

For no-agent setup run `speckit-gate init --interactive` or
`speckit-gate init --defaults`.

## Harness enforcement matrix

| Harness | Install path | Enforcement |
|---------|-------------|-------------|
| Claude Code (`claude`) | Plugin or `install --harness claude` | **deny** (PreToolUse:Skill + PreToolUse:Agent + UserPromptExpansion) |
| Codex CLI (`codex`) | `install --harness codex` | **deny** (UserPromptSubmit + PreToolUse) |
| Cursor (`cursor-agent`) | spec-kit bundle | advisory |
| GitHub Copilot (`copilot`) | spec-kit bundle | advisory |
| Gemini CLI (`gemini`) | spec-kit bundle | advisory |
| Zed (`zed`) | spec-kit bundle | advisory |
| Amp (`amp`) | spec-kit bundle | advisory |
| Augment (`auggie`) | spec-kit bundle | advisory |
| Cline (`cline`) | spec-kit bundle | advisory |
| Trae (`trae`) | spec-kit bundle | advisory |
| ZCode (`zcode`) | spec-kit bundle | advisory |
| Kimi Code (`kimi`) | spec-kit bundle | advisory |
| Firebender (`firebender`) | spec-kit bundle | advisory |
| Goose (`goose`) | spec-kit bundle | advisory |
| Devin (`devin`) | spec-kit bundle | advisory |
| Junie (`junie`) | spec-kit bundle | advisory |
| Lingma (`lingma`) | spec-kit bundle | advisory |
| All other spec-kit harnesses | spec-kit bundle | advisory |

**deny** = the hook emits `permissionDecision: deny` or `decision: block`,
preventing the tool from running.

**advisory** = the gate injects prerequisite context into the model's context
window (via spec-kit's `before_*` hook infrastructure) but does not block
execution.

### Bundle adapter rationale

spec-kit supports 36+ harnesses.  Of these, only Claude Code and Codex expose
a real hook system (PreToolUse / UserPromptExpansion / UserPromptSubmit) that
can deny tool calls before they run.  All other harnesses receive spec-kit's
advisory prompt injection as their only integration path — there is no hook
event to intercept.

The spec-kit bundle is therefore the **only** distribution path that reaches
advisory harnesses.  It ships an extension that registers `/speckit.gate.init`
and emits prerequisite context before each spec-kit command via spec-kit's
built-in `before_*` advisory hooks.

The bundle does not duplicate Claude Code or Codex enforcement — those
harnesses should use the plugin or `install --harness` path for real deny
gates.

## CLI reference

| Verb | Description |
|------|-------------|
| `scan` | Scan project for spec-kit commands |
| `propose` | Show prerequisite proposal table |
| `init` | Write `gates.yaml` (--defaults / --answers / --interactive) |
| `compile` | Compile `gates.yaml` → `.specify/gates/nodes.json` |
| `compile --check` | Drift check only; exit 1 if stale |
| `install --harness` | Install hook adapters (claude/codex/speckit/all) |
| `explain <cmd>` | Show prerequisites for a command |
| `dry-run <cmd>` | Simulate a hook event |
| `dispatch pre|post` | Internal: hook dispatcher (stdin JSON → stdout JSON) |

## gates.yaml schema

```yaml
config:
  prefix: speckit.          # command prefix; default "speckit."
  feature_root: specs       # feature artefact root; default "specs"
  resolve: [git-branch, newest-dir]
  messages:
    no_feature: "..."       # block reason when no feature resolved

gates:
  <command>:
    requires: [cmd-or-artefact, ...]
    produces: [artefact, ...]
    deprecated: true|false
    spawn_agent: true|false  # adds PreToolUse:Agent gate (Claude only)
    context: "..."           # advisory context injected into the model
```

`compile` derives edges by matching `produces` → `requires` and writes
`.specify/gates/nodes.json` in the flat dispatcher format the hook reads.

## Presets

| Preset | Description |
|--------|-------------|
| `presets/core.gates.yaml` | All spec-kit built-in commands |
| `presets/srobroek-full.gates.yaml` | Full 28-node DAG with agent-assign extension and spawn_agent gates |

Copy a preset as your starting `gates.yaml`:

```bash
cp $(uvx speckit-gate --version && echo "") /dev/null  # just to confirm uvx works
curl -sL https://raw.githubusercontent.com/srobroek/speckit-gate/main/presets/core.gates.yaml \
  > gates.yaml
speckit-gate compile
```

## Plain-python fallback

For exec-tax-sensitive environments (slow filesystem, EDR overhead) where
`uvx` startup latency matters even with caching, use the installed console
script directly:

```bash
pip install speckit-gate  # or uv pip install speckit-gate
# then in hooks.json:
# "command": "speckit-gate dispatch pre"
```

The dispatcher (`dispatch.py`) is stdlib-only with no import overhead.
`uvx` caches after first run and is the default wiring; switch to the
installed path only when profiling shows hook latency is a problem.

## Development

```bash
uv sync --dev
uv run pytest
uv run speckit-gate --help
```

## License

Apache-2.0
