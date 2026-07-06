"""Command-line interface for speckit-gate.

Verbs:
  scan        Scan a project for spec-kit commands in use
  propose     Show a prerequisite proposal table for scanned commands
  init        Initialise a gates.yaml (--interactive | --answers FILE | --defaults)
  compile     Compile gates.yaml → .specify/gates/nodes.json (--check for drift)
  install     Install harness adapters (--harness claude|codex|speckit|all)
  explain     Explain prerequisites for a command
  dry-run     Show what gates would fire for a simulated event
  dispatch    Internal: run the dispatcher (used by hook wiring)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

from speckit_gate import __version__


def _cmd_scan(args: argparse.Namespace) -> int:
    from speckit_gate.scan import scan_project
    root = args.root or os.getcwd()
    commands = scan_project(root)
    if not commands:
        print("No spec-kit commands found in project.")
        return 0
    print("Detected spec-kit commands:")
    for cmd in commands:
        print(f"  {cmd}")
    return 0


def _cmd_propose(args: argparse.Namespace) -> int:
    from speckit_gate.scan import scan_project
    from speckit_gate.propose import propose, format_proposal_table
    root = args.root or os.getcwd()
    commands = scan_project(root)
    if not commands:
        print("No spec-kit commands found.")
        return 0
    proposal = propose(commands)
    print(format_proposal_table(proposal))
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    root = args.root or os.getcwd()
    from speckit_gate.scan import scan_project
    from speckit_gate.propose import propose, format_proposal_table
    from speckit_gate.known_gates import KNOWN_GATES

    commands = scan_project(root)
    proposal = propose(commands)

    if args.defaults:
        _write_default_gates_yaml(root, proposal)
        print("Wrote gates.yaml with defaults.")
        return 0

    if args.answers:
        _write_gates_yaml_from_answers(root, args.answers)
        print("Wrote gates.yaml from answers file.")
        return 0

    # --interactive: print the table and a note for agent-driven use
    print("=== speckit-gate: gate initialisation ===\n")
    print(format_proposal_table(proposal))
    if proposal["unknown"]:
        print(
            "\nUnknown commands require manual requires/produces definitions."
            "\nFor agent-driven setup, use the speckit-gate SKILL.md skill."
        )
    _write_default_gates_yaml(root, proposal)
    print("\nWrote initial gates.yaml — review and adjust requires/produces.")
    return 0


def _write_default_gates_yaml(root: str, proposal: dict) -> None:
    from speckit_gate.known_gates import KNOWN_GATES
    os.makedirs(root, exist_ok=True)
    out_path = os.path.join(root, "gates.yaml")
    lines = [
        "# speckit-gate configuration",
        "# See https://github.com/srobroek/speckit-gate for docs",
        "",
        "config:",
        "  prefix: speckit.",
        "  feature_root: specs",
        "  resolve: [git-branch, newest-dir]",
        "  messages:",
        "    no_feature: >-",
        "      No active spec-kit feature resolved.",
        "      Run /speckit.specify first or switch to the feature branch.",
        "",
        "gates:",
    ]
    all_cmds = dict(proposal["known"])
    # Add unknowns with empty stubs
    for cmd in proposal["unknown"]:
        all_cmds[cmd] = {"requires": [], "produces": [], "context": "TODO: define prerequisites"}

    for cmd in sorted(all_cmds):
        info = all_cmds[cmd]
        requires = info.get("requires") or []
        produces = info.get("produces") or []
        ctx = info.get("context") or ""
        deprecated = info.get("deprecated") or False
        spawn = info.get("spawn_agent") or False
        lines.append(f"  {cmd}:")
        if deprecated:
            lines.append(f"    deprecated: true")
        if spawn:
            lines.append(f"    spawn_agent: true")
        if requires:
            req_str = "[" + ", ".join(requires) + "]"
            lines.append(f"    requires: {req_str}")
        else:
            lines.append("    requires: []")
        if produces:
            prod_str = "[" + ", ".join(produces) + "]"
            lines.append(f"    produces: {prod_str}")
        else:
            lines.append("    produces: []")
        if ctx:
            lines.append(f"    context: >-")
            lines.append(f"      {ctx}")
        lines.append("")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def _write_gates_yaml_from_answers(root: str, answers_path: str) -> None:
    """Load an answers JSON file and write gates.yaml from it.

    answers.json shape:
      {
        "commands": {
          "my-cmd": {"requires": [...], "produces": [...], "context": "..."}
        },
        "config": { ... }
      }
    """
    with open(answers_path, "r", encoding="utf-8") as fh:
        answers = json.load(fh)

    from speckit_gate.scan import scan_project
    from speckit_gate.propose import propose

    commands = scan_project(root)
    proposal = propose(commands)

    # Merge answers into proposal
    for cmd, info in (answers.get("commands") or {}).items():
        proposal["known"][cmd] = info
        if cmd in proposal["unknown"]:
            proposal["unknown"].remove(cmd)

    _write_default_gates_yaml(root, proposal)


def _cmd_compile(args: argparse.Namespace) -> int:
    from speckit_gate.compile import compile_gates, check_drift

    root = args.root or os.getcwd()
    gates_yaml = args.gates_yaml or os.path.join(root, "gates.yaml")
    if not os.path.isfile(gates_yaml):
        print(f"Error: gates.yaml not found at {gates_yaml}", file=sys.stderr)
        return 1

    try:
        nodes, cfg, warnings = compile_gates(gates_yaml)
    except Exception as exc:
        print(f"Compile error: {exc}", file=sys.stderr)
        return 1

    if warnings:
        print("Compile warnings:", file=sys.stderr)
        for w in warnings:
            print(w, file=sys.stderr)

    # Store config header in nodes for dispatcher
    output = {"_config": cfg, **nodes}
    nodes_dir = os.path.join(root, ".specify", "gates")
    nodes_path = os.path.join(nodes_dir, "nodes.json")

    if args.check:
        has_drift, diff = check_drift(output, nodes_path)
        if has_drift:
            print("DRIFT detected — run `speckit-gate compile` to regenerate.", file=sys.stderr)
            if diff:
                print(diff, file=sys.stderr)
            return 1
        print("nodes.json is in sync.", file=sys.stderr)
        return 0

    os.makedirs(nodes_dir, exist_ok=True)
    with open(nodes_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"Compiled {len(nodes)} gates → {nodes_path}")
    return 0


def _cmd_install(args: argparse.Namespace) -> int:
    root = args.root or os.getcwd()
    harness = args.harness or "all"

    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    adapters_dir = os.path.join(here, "adapters")

    if harness in ("claude", "all"):
        _install_claude(root, adapters_dir)
    if harness in ("codex", "all"):
        _install_codex(root, adapters_dir)
    if harness in ("speckit", "all"):
        print(
            "speckit bundle adapter: install via `specify bundle install speckit-gate`"
            " once the bundle is registered in the community catalog.",
            file=sys.stderr,
        )
    return 0


def _install_claude(root: str, adapters_dir: str) -> None:
    src = os.path.join(adapters_dir, "claude", "hooks.json")
    dst_dir = os.path.join(root, ".claude")
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, "hooks.json")
    if os.path.isfile(src):
        shutil.copy2(src, dst)
        print(f"Installed Claude adapter → {dst}")
    else:
        print(f"Claude adapter not found at {src}", file=sys.stderr)


def _install_codex(root: str, adapters_dir: str) -> None:
    src = os.path.join(adapters_dir, "codex", "hooks.json")
    dst_dir = os.path.join(root, ".codex")
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, "hooks.json")
    if os.path.isfile(src):
        shutil.copy2(src, dst)
        print(f"Installed Codex adapter → {dst}")
    else:
        print(f"Codex adapter not found at {src}", file=sys.stderr)


def _cmd_explain(args: argparse.Namespace) -> int:
    from speckit_gate.known_gates import KNOWN_GATES, COMMUNITY_EXTENSION_GATES
    cmd = args.command
    # Strip prefix
    for prefix in ("speckit.", "speckit-", "/speckit."):
        if cmd.startswith(prefix):
            cmd = cmd[len(prefix):]
            break
    cmd = cmd.replace(".", "-")
    all_known = {**KNOWN_GATES, **COMMUNITY_EXTENSION_GATES}
    info = all_known.get(cmd)
    if not info:
        print(f"Unknown command: {cmd}")
        print("No default gate definition found. Check gates.yaml for project-local config.")
        return 0
    print(f"Command: speckit.{cmd.replace('-', '.')}")
    print(f"  Requires: {', '.join(info.get('requires') or []) or '(none)'}")
    print(f"  Produces: {', '.join(info.get('produces') or []) or '(none)'}")
    if info.get("context"):
        print(f"  Context:  {info['context']}")
    if info.get("deprecated"):
        print("  DEPRECATED")
    if info.get("spawn_agent"):
        print("  spawn_agent: true (requires PreToolUse:Agent support)")
    return 0


def _cmd_dry_run(args: argparse.Namespace) -> int:
    """Simulate a hook event and show what the dispatcher would emit."""
    from speckit_gate.dispatch import dispatch as _dispatch
    import io

    event = args.event or "UserPromptExpansion"
    command = args.command or ""
    root = args.root or os.getcwd()

    payload = {
        "hook_event_name": event,
        "command_name": command,
        "cwd": root,
        "tool_input": {"skill": command},
    }

    phase = args.phase or "pre"
    nodes_path = args.nodes or os.path.join(root, ".specify", "gates", "nodes.json")

    old_stdin = sys.stdin
    old_stdout = sys.stdout
    sys.stdin = io.StringIO(json.dumps(payload))
    sys.stdout = io.StringIO()
    try:
        _dispatch(phase, nodes_path if os.path.isfile(nodes_path) else None)
        output = sys.stdout.getvalue()
    finally:
        sys.stdin = old_stdin
        sys.stdout = old_stdout

    if output:
        try:
            parsed = json.loads(output)
            print(json.dumps(parsed, indent=2))
        except ValueError:
            print(output)
    else:
        print("(no gate fired — command not found in nodes.json)")
    return 0


def _cmd_dispatch(args: argparse.Namespace) -> int:
    """Internal dispatch verb: reads stdin, writes hook response to stdout."""
    from speckit_gate.dispatch import dispatch as _dispatch
    phase = args.phase or "pre"
    nodes_path = args.nodes or None
    return _dispatch(phase, nodes_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="speckit-gate",
        description="Harness-agnostic workflow gates for spec-kit projects.",
    )
    parser.add_argument("--version", action="version", version=f"speckit-gate {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # scan
    p = sub.add_parser("scan", help="Scan project for spec-kit commands")
    p.add_argument("--root", help="Project root (default: cwd)")

    # propose
    p = sub.add_parser("propose", help="Show prerequisite proposal table")
    p.add_argument("--root", help="Project root (default: cwd)")

    # init
    p = sub.add_parser("init", help="Initialise gates.yaml")
    p.add_argument("--root", help="Project root (default: cwd)")
    p.add_argument("--interactive", action="store_true", help="Interactive mode")
    p.add_argument("--answers", metavar="FILE", help="Answers JSON file")
    p.add_argument("--defaults", action="store_true", help="Use defaults without prompting")

    # compile
    p = sub.add_parser("compile", help="Compile gates.yaml → .specify/gates/nodes.json")
    p.add_argument("--root", help="Project root (default: cwd)")
    p.add_argument("--gates-yaml", help="Path to gates.yaml (default: <root>/gates.yaml)")
    p.add_argument("--check", action="store_true", help="Diff only; exit 1 on drift")

    # install
    p = sub.add_parser("install", help="Install harness adapter hooks")
    p.add_argument("--root", help="Project root (default: cwd)")
    p.add_argument(
        "--harness",
        choices=["claude", "codex", "speckit", "all"],
        default="all",
        help="Which harness to install",
    )

    # explain
    p = sub.add_parser("explain", help="Explain gates for a command")
    p.add_argument("command", help="Command name (e.g. speckit.plan or plan)")

    # dry-run
    p = sub.add_parser("dry-run", help="Simulate a hook event")
    p.add_argument("command", nargs="?", help="Command name")
    p.add_argument("--root", help="Project root (default: cwd)")
    p.add_argument("--event", default="UserPromptExpansion", help="Hook event type")
    p.add_argument("--phase", default="pre", choices=["pre", "post"])
    p.add_argument("--nodes", help="Path to nodes.json")

    # dispatch (internal)
    p = sub.add_parser("dispatch", help="Internal: run dispatcher from hook")
    p.add_argument("phase", choices=["pre", "post"])
    p.add_argument("--nodes", help="Path to nodes.json")

    ns = parser.parse_args(argv)
    dispatch_table = {
        "scan": _cmd_scan,
        "propose": _cmd_propose,
        "init": _cmd_init,
        "compile": _cmd_compile,
        "install": _cmd_install,
        "explain": _cmd_explain,
        "dry-run": _cmd_dry_run,
        "dispatch": _cmd_dispatch,
    }
    return dispatch_table[ns.cmd](ns)


if __name__ == "__main__":
    sys.exit(main())
