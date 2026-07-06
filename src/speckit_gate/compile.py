"""Compile a gates.yaml file into .specify/gates/nodes.json.

gates.yaml schema (subset implemented here):
  config:
    prefix: "speckit."          # command prefix to strip when matching
    feature_root: "specs"       # root dir for feature artefacts
    resolve: [git-branch, newest-dir]
    messages:
      no_feature: "..."         # block reason when no feature resolved
  gates:
    <cmd>:
      requires: [cmd, ...]      # prerequisite commands (produces → requires matching)
      produces: [artefact, ...] # artefacts this command creates
      deprecated: true|false
      spawn_agent: true|false   # gate form: agent:<name> for claude PreToolUse Agent
      context: "..."            # advisory context text

compile() derives edges by matching each gate's 'produces' against other
gates' 'requires'.  It then emits nodes.json in the flat dispatcher format:

  {node_id: {"pre": {...}, "post": {...}}}

--check mode diffs the compiled output against the existing nodes.json and
exits 1 on drift.
"""

from __future__ import annotations

import difflib
import json
import os
import sys
from typing import Any

from speckit_gate._yaml import load_yaml


_DEFAULT_CONFIG = {
    "prefix": "speckit.",
    "feature_root": "specs",
    "resolve": ["git-branch", "newest-dir"],
    "messages": {
        "no_feature": (
            "No active spec-kit feature resolved — run /speckit.specify first"
            " or switch to the feature branch"
        ),
    },
}


class CompileError(Exception):
    pass


def _merge_config(raw: dict) -> dict:
    cfg = dict(_DEFAULT_CONFIG)
    cfg["messages"] = dict(_DEFAULT_CONFIG["messages"])
    raw_cfg = raw.get("config") or {}
    cfg.update({k: v for k, v in raw_cfg.items() if k != "messages"})
    if "messages" in raw_cfg and isinstance(raw_cfg["messages"], dict):
        cfg["messages"].update(raw_cfg["messages"])
    return cfg


def compile_gates(gates_yaml_path: str) -> dict:
    """Load gates.yaml and return the compiled nodes dict."""
    with open(gates_yaml_path, "r", encoding="utf-8") as fh:
        raw = load_yaml(fh.read())
    if not isinstance(raw, dict):
        raise CompileError("gates.yaml must be a YAML mapping at the top level")

    cfg = _merge_config(raw)
    gates_raw = raw.get("gates") or {}
    if not isinstance(gates_raw, dict):
        raise CompileError("gates.yaml: 'gates' must be a mapping")

    nodes: dict[str, Any] = {}
    warnings: list[str] = []

    # Build a produces -> [cmd] index for edge derivation
    produces_index: dict[str, list[str]] = {}
    for cmd, info in gates_raw.items():
        if not isinstance(info, dict):
            continue
        for prod in info.get("produces") or []:
            produces_index.setdefault(prod, []).append(cmd)

    prefix = cfg.get("prefix", "speckit.")
    feature_root = cfg.get("feature_root", "specs")

    for cmd, info in gates_raw.items():
        if not isinstance(info, dict):
            continue

        node_id = cmd

        deprecated = bool(info.get("deprecated"))
        spawn_agent = bool(info.get("spawn_agent"))
        context_text = info.get("context") or ""
        requires = list(info.get("requires") or [])
        produces = list(info.get("produces") or [])

        # Check spawn_agent harness support warning
        if spawn_agent:
            warnings.append(
                f"  {node_id}: spawn_agent=true — harnesses without PreToolUse:Agent "
                "support (codex, bundle) will skip this gate (advisory-only)."
            )

        # Build hard_missing from requires
        hard_missing: list[str] = []
        hard_deprecated: list[str] = []
        hard_exists: list[str] = []

        if deprecated:
            cmd_name = prefix + cmd.replace("-", ".")
            hard_deprecated.append(
                f"/{cmd_name} is deprecated in this project. "
                f"See gates.yaml for the recommended replacement."
            )
        else:
            for req in requires:
                # Check if req is an artefact path or a command name
                if "/" in req or req.startswith("specs/") or "." in req.split("/")[-1]:
                    # It's an artefact path
                    hard_missing.append(req)
                else:
                    # It's a command name; look up its produces artefacts
                    req_info = gates_raw.get(req)
                    if req_info and isinstance(req_info, dict):
                        for prod in req_info.get("produces") or []:
                            if "<feat>" in prod or "/" in prod:
                                hard_missing.append(prod)
                    # else: req is a bare label like 'sync-report', 'bugfix-report'
                    # Use a heuristic: specs/<feat>/<req>.md
                    elif req not in gates_raw:
                        hard_missing.append(f"{feature_root}/<feat>/{req}.md")

        # Build produces artefacts for hard_exists (re-run guard)
        for prod in produces:
            if "<feat>" in prod or "/" in prod:
                # Only guard on .md artefacts to avoid false positives on dirs
                if prod.endswith(".md") or prod.endswith(".yml"):
                    hard_exists.append(prod)

        # came_from / going_to derived from edges
        came_from: list[str] = []
        going_to: list[str] = []
        for req in requires:
            if req in gates_raw:
                came_from.append(f"/{prefix}{req.replace('-', '.')} (mandatory)")
        for prod in produces:
            for consumer in produces_index.get(prod, []):
                if consumer != cmd:
                    going_to.append(f"/{prefix}{consumer.replace('-', '.')} (default)")

        pre: dict = {
            "title": f"/{prefix}{cmd.replace('-', '.')} -- before you run this",
            "soft": [],
        }
        if came_from:
            pre["came_from"] = came_from
        if hard_deprecated:
            pre["hard_deprecated"] = hard_deprecated
        if hard_missing:
            pre["hard_missing"] = hard_missing
        if hard_exists:
            pre["hard_exists"] = hard_exists
        if context_text:
            pre["context"] = [context_text]

        post: dict = {
            "title": f"/{prefix}{cmd.replace('-', '.')} -- what to do next",
        }
        if going_to:
            post["going_to"] = going_to
        if produces:
            post["postconditions"] = [f"`{p}`" for p in produces]

        nodes[node_id] = {"pre": pre, "post": post}

    return nodes, cfg, warnings


def check_drift(nodes: dict, nodes_json_path: str) -> tuple[bool, str]:
    """Compare compiled nodes against the on-disk nodes.json.
    Returns (has_drift, diff_text).
    """
    generated = json.dumps(nodes, indent=2, sort_keys=True) + "\n"
    if not os.path.isfile(nodes_json_path):
        return True, "DRIFT: nodes.json is missing"
    with open(nodes_json_path, "r", encoding="utf-8") as fh:
        on_disk = fh.read()
    # Normalise for comparison
    try:
        on_disk_norm = json.dumps(json.loads(on_disk), indent=2, sort_keys=True) + "\n"
    except (ValueError, OSError):
        return True, "DRIFT: nodes.json is malformed"
    if generated == on_disk_norm:
        return False, ""
    diff = "".join(
        difflib.unified_diff(
            on_disk_norm.splitlines(keepends=True),
            generated.splitlines(keepends=True),
            fromfile="nodes.json (on disk)",
            tofile="nodes.json (compiled)",
        )
    )
    return True, "DRIFT detected:\n" + diff
