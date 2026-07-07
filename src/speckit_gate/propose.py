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


def format_proposal_table(proposal: dict, fmt: str = "aligned") -> str:
    """Render the proposal as a table for display.

    fmt="aligned"  — fixed-width padded columns suitable for terminal output
    fmt="md"       — markdown pipe table suitable for rendered docs / agents
    """
    rows: list[tuple[str, str, str, str]] = []
    for cmd, info in sorted(proposal["known"].items()):
        requires = ", ".join(info.get("requires") or []) or ""
        produces = ", ".join(info.get("produces") or []) or ""
        notes = []
        if info.get("deprecated"):
            notes.append("DEPRECATED")
        if info.get("spawn_agent"):
            notes.append("spawn_agent")
        note_str = "; ".join(notes) if notes else ""
        rows.append((cmd, requires, produces, note_str))

    if fmt == "md":
        lines = [
            "| Command | Requires | Produces | Notes |",
            "|---------|----------|----------|-------|",
        ]
        for cmd, requires, produces, notes in rows:
            lines.append(f"| `{cmd}` | {requires or '(none)'} | {produces or '(none)'} | {notes} |")
        if proposal["unknown"]:
            lines.append("")
            lines.append("**Unknown commands (need interview):**")
            for cmd in proposal["unknown"]:
                lines.append(f"- `{cmd}`")
        return "\n".join(lines)

    # aligned (default) — plain text, fixed-width columns
    headers = ("Command", "Requires", "Produces", "Notes")
    col_w = [len(h) for h in headers]
    for cmd, requires, produces, notes in rows:
        col_w[0] = max(col_w[0], len(cmd))
        col_w[1] = max(col_w[1], len(requires))
        col_w[2] = max(col_w[2], len(produces))
        col_w[3] = max(col_w[3], len(notes))

    def _row(cells: tuple[str, ...]) -> str:
        parts = [c.ljust(col_w[i]) for i, c in enumerate(cells)]
        # Strip trailing whitespace on the last column
        parts[-1] = parts[-1].rstrip()
        return "  " + "  ".join(parts)

    lines = [_row(headers)]
    for row in rows:
        lines.append(_row(row))

    if proposal["unknown"]:
        lines.append("")
        lines.append("Unknown commands (need interview):")
        for cmd in proposal["unknown"]:
            lines.append(f"  {cmd}")

    return "\n".join(lines)
