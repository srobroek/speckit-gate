"""Generate a gate proposal table for scanned commands.

Takes a list of commands (from scan.py) and produces a structured proposal
mapping each command to its known prerequisites, marking unknowns separately
so the interview step can ask about them.
"""

from __future__ import annotations

from speckit_gate.known_gates import KNOWN_GATES, COMMUNITY_EXTENSION_GATES


def propose(commands: list[str]) -> dict:
    """Return a proposal dict:
        {
          "known":   {cmd: {requires, produces, context, deprecated?, spawn_agent?}},
          "unknown": [cmd, ...],
        }
    """
    all_known = {**KNOWN_GATES, **COMMUNITY_EXTENSION_GATES}
    known: dict[str, dict] = {}
    unknown: list[str] = []
    for cmd in sorted(commands):
        if cmd in all_known:
            known[cmd] = dict(all_known[cmd])
        else:
            unknown.append(cmd)
    return {"known": known, "unknown": unknown}


def format_proposal_table(proposal: dict) -> str:
    """Render the proposal as a markdown table for display in the interview."""
    lines = [
        "| Command | Requires | Produces | Notes |",
        "|---------|----------|----------|-------|",
    ]
    for cmd, info in sorted(proposal["known"].items()):
        requires = ", ".join(info.get("requires") or []) or "(none)"
        produces = ", ".join(info.get("produces") or []) or "(none)"
        notes = []
        if info.get("deprecated"):
            notes.append("DEPRECATED")
        if info.get("spawn_agent"):
            notes.append("spawn_agent")
        note_str = "; ".join(notes) if notes else ""
        lines.append(f"| `{cmd}` | {requires} | {produces} | {note_str} |")

    if proposal["unknown"]:
        lines.append("")
        lines.append("**Unknown commands (need interview):**")
        for cmd in proposal["unknown"]:
            lines.append(f"- `{cmd}`")

    return "\n".join(lines)
