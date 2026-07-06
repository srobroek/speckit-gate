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

A gate is only as strong as its blindest channel, and every harness differs by
**invocation channel**: what happens when the *user* types a command vs. when
the *model* (a workflow engine, a subagent) evokes one mid-run. A gate that
covers only the user channel is silently bypassed by agent-driven runs — so the
matrix is per-channel. All deny rows below are verified against harness source
(mid-2026); adapters currently ship for Claude Code and Codex.

| Harness | User invocation | Model/agent evocation | Adapter |
|---------|-----------------|----------------------|---------|
| Claude Code | **deny** — `UserPromptExpansion`, sees command name | **deny** — `PreToolUse: Skill\|Agent` | shipped |
| Qwen Code | **deny** — `UserPromptExpansion`, sees `command_name` (+ `UserPromptSubmit` post-expansion) | **deny** — `PreToolUse` on `skill`/`agent` tools (full prompt); model-invoked commands re-fire `UserPromptExpansion`. `SubagentStart` cannot block | planned |
| Codex CLI | **deny** — `UserPromptSubmit` (raw human text; text-match, no command structure; requires `[features] hooks = true`) | **none** — skills inject as context with no event; `SubagentStart` is metadata-only (`continue:false` at best). Artifact gates are the backstop | shipped |
| Gemini CLI | **deny** — `BeforeAgent` (expanded template text only — no command name, no slash-origin marker; content-match required) | **n/a** — model cannot invoke `.toml` commands by design | planned |
| Mistral Vibe | **none** — slash/skill input expands in the UI layer, invisible to hooks | **deny** — `before_tool` on the `skill` tool (sees skill name; flag: `enable_experimental_hooks`). Note: skill loads bypass Vibe's user-approval prompt, so this hook is the only programmatic gate | planned |
| Amp | observe-only — `agent.start` sees prompt text but cannot block | **deny** — `tool.call` verdicts on subagent/delegation tools (skill-load visibility unverified). Note: spec-kit ≤0.12.4 renders Amp commands to `.agents/commands/`, removed by Amp 2026-01 — its Amp integration is currently broken upstream | — |
| GitHub Copilot | hooks exist; deny semantics unverified | unverified | — |
| Cursor, Zed, Cline, Goose, Devin, Trae, Lingma, Kimi, ZCode, Firebender, Junie, Auggie, + ~14 more | static context only — no hook system | static context only | spec-kit bundle (advisory text) |

Where a channel shows **none**/static, enforcement falls back to **artifact
gates**: a downstream gated command hard-requires the report file the skipped
step should have produced, so out-of-order runs still fail at the next
enforceable point.

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
