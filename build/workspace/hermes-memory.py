#!/usr/bin/env python3
"""
hermes-memory — Team Shared Memory Layer.

Implements Moxt.ai's killer feature: "纠正一个 Agent 犯的错，团队里所有 Agent 都记住了"
(Correct one agent's mistake, ALL agents in the team remember it).

Reads from and writes to a shared memory file (SHARED_MEMORY.md) that all
coworkers consume before executing.  Corrections propagate instantly to every
agent in the team.

Usage (CLI):
    hermes-memory.py show                    # display full shared memory
    hermes-memory.py add "correction text"   # add a correction entry
    hermes-memory.py search "keyword"        # search memory by keyword
    hermes-memory.py context                 # print compressed context for coworker injection

Usage (Python API):
    from hermes_memory import SharedMemory
    mem = SharedMemory()
    mem.read_memory("shared")
    mem.write_memory("correction text", "human:CEO")
    mem.correct_memory("entry-id", "new content")
    mem.search_memory("keyword")
    mem.get_team_context()  # compressed context for prompts

Memory entry format in SHARED_MEMORY.md:
    ## [2026-05-14 14:30] ops/morning-brief
    修正：竞品监控应包含 GitHub trending 而非仅官网。

Dependencies: Python 3.8+
"""

from __future__ import annotations

import argparse
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent  # -> ~/.hermes/workspace
DEFAULT_MEMORY_FILE = PROJECT_ROOT / "SHARED_MEMORY.md"


# ---------------------------------------------------------------------------
# Entry format helpers
# ---------------------------------------------------------------------------
ENTRY_HEADER_RE = re.compile(
    r"^##\s+\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\]\s+(.+?)\s*$"
)


def _make_timestamp() -> str:
    """Return current UTC timestamp in memory-entry format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


def _make_entry_id() -> str:
    """Generate a short unique ID for a memory entry."""
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# SharedMemory — the importable Python API
# ---------------------------------------------------------------------------
class SharedMemory:
    """Team shared memory layer backed by SHARED_MEMORY.md."""

    def __init__(self, memory_file: Optional[Path] = None):
        """
        Args:
            memory_file: Path to the shared memory markdown file.
                         Defaults to PROJECT_ROOT / "SHARED_MEMORY.md".
        """
        self.memory_file = Path(memory_file) if memory_file else DEFAULT_MEMORY_FILE

    # ------------------------------------------------------------------
    # read_memory — returns full memory content
    # ------------------------------------------------------------------
    def read_memory(self, scope: str = "shared") -> str:
        """Return the full contents of the shared memory file.

        Args:
            scope: Reserved for future expansion (e.g. "team", "board").
                   Currently only "shared" is implemented.

        Returns:
            Full text of SHARED_MEMORY.md, or empty string if it doesn't exist.
        """
        if not self.memory_file.exists():
            return ""
        return self.memory_file.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # write_memory — append a timestamped entry
    # ------------------------------------------------------------------
    def write_memory(
        self,
        entry: str,
        author: str = "unknown",
        scope: str = "shared",
    ) -> dict:
        """Append a timestamped entry to the shared memory file.

        Args:
            entry: The correction / learning text to append.
            author: Who authored this memory (e.g. "human:CEO", "ops/morning-brief").
            scope: Memory scope (currently only "shared").

        Returns:
            {"success": True, "entry_id": "...", "header": "..."}
        """
        entry_id = _make_entry_id()
        timestamp = _make_timestamp()
        header = f"## [{timestamp}] {author}"

        # Build the new entry block
        body_lines = [line for line in entry.strip().split("\n")]
        entry_block = header + "\n" + "\n".join(body_lines) + "\n"

        # Initialize file if it doesn't exist
        if not self.memory_file.exists():
            self.memory_file.parent.mkdir(parents=True, exist_ok=True)
            self.memory_file.write_text(
                "# Team Shared Memory\n\n"
                "> 纠正一个 Agent 犯的错，团队里所有 Agent 都记住了。\n"
                "> Correct one agent's mistake, ALL agents remember it.\n\n",
                encoding="utf-8",
            )

        # Append
        with open(self.memory_file, "a", encoding="utf-8") as f:
            f.write("\n" + entry_block)

        return {
            "success": True,
            "entry_id": entry_id,
            "header": header,
            "author": author,
            "timestamp": timestamp,
        }

    # ------------------------------------------------------------------
    # correct_memory — update a specific entry by its timestamp+author header
    # ------------------------------------------------------------------
    def correct_memory(
        self,
        correction_id: str,
        new_content: str,
    ) -> dict:
        """Update a specific memory entry in-place.

        This is the key 'correct once, all learn' operation.  A human or agent
        fixes a single entry and the correction is instantly visible to every
        coworker.

        Args:
            correction_id: A string that uniquely identifies the entry header.
                           This is matched against the entry header line
                           (e.g. "[2026-05-14 14:30] ops/morning-brief").
            new_content: The replacement body text for the entry (without
                         the header line, which is preserved).

        Returns:
            {"success": True/False, "matched": int}
        """
        if not self.memory_file.exists():
            return {"success": False, "error": "Memory file not found", "matched": 0}

        lines = self.memory_file.read_text(encoding="utf-8").split("\n")
        new_lines: list[str] = []
        matched = 0
        in_target = False
        header_line = ""

        for i, line in enumerate(lines):
            m = ENTRY_HEADER_RE.match(line)
            if m:
                # We hit a new entry header
                if in_target:
                    # We were inside a matched entry — write the correction body
                    new_lines.append(header_line)
                    for body_line in new_content.strip().split("\n"):
                        new_lines.append(body_line)
                    in_target = False

                # Check if this entry matches the correction_id
                full_header = m.group(0).lstrip("#").strip()
                full_date_author = f"[{m.group(1)}] {m.group(2)}"
                if (
                    correction_id in full_header
                    or correction_id in full_date_author
                    or correction_id in m.group(2)
                ):
                    in_target = True
                    header_line = line
                    matched += 1
                    continue

            if not in_target:
                new_lines.append(line)

        # Handle case where matched entry is the last one
        if in_target:
            new_lines.append(header_line)
            for body_line in new_content.strip().split("\n"):
                new_lines.append(body_line)

        if matched == 0:
            return {"success": False, "error": "No matching entry found", "matched": 0}

        self.memory_file.write_text("\n".join(new_lines), encoding="utf-8")
        return {"success": True, "matched": matched}

    # ------------------------------------------------------------------
    # search_memory — keyword search across all entries
    # ------------------------------------------------------------------
    def search_memory(self, query: str) -> list[dict]:
        """Search the shared memory by keyword (case-insensitive).

        Args:
            query: Keyword or phrase to search for.

        Returns:
            List of matching entries, each as {"header": ..., "body": ..., "lines": (start, end)}.
        """
        if not self.memory_file.exists():
            return []

        lines = self.memory_file.read_text(encoding="utf-8").split("\n")
        query_lower = query.lower()
        results: list[dict] = []
        current_header: Optional[str] = None
        current_body_lines: list[str] = []
        current_start: int = 0

        for i, line in enumerate(lines):
            m = ENTRY_HEADER_RE.match(line)
            if m:
                # Flush previous entry
                if current_header is not None:
                    body_text = "\n".join(current_body_lines)
                    if query_lower in current_header.lower() or query_lower in body_text.lower():
                        results.append({
                            "header": current_header.strip().lstrip("#").strip(),
                            "body": body_text,
                            "line_start": current_start,
                            "line_end": i - 1,
                        })
                # Start new entry
                current_header = line
                current_body_lines = []
                current_start = i
            else:
                current_body_lines.append(line)

        # Flush last entry
        if current_header is not None:
            body_text = "\n".join(current_body_lines)
            if query_lower in current_header.lower() or query_lower in body_text.lower():
                results.append({
                    "header": current_header.strip().lstrip("#").strip(),
                    "body": body_text,
                    "line_start": current_start,
                    "line_end": len(lines) - 1,
                })

        return results

    # ------------------------------------------------------------------
    # get_team_context — compressed context for coworker prompt injection
    # ------------------------------------------------------------------
    def get_team_context(self, max_entries: int = 20) -> str:
        """Return a compressed, prompt-injectable summary of the shared memory.

        This is the main integration point: call this before each coworker run
        and inject the result into the coworker's execution context.

        The context includes:
        - Most recent N entries (newest first)
        - A highlight section for human-authored corrections
        - Total memory stats

        Args:
            max_entries: Maximum number of recent entries to include.

        Returns:
            A compact string ready for injection into an LLM prompt.
        """
        if not self.memory_file.exists():
            return (
                "[Team Shared Memory]\n"
                "No shared memory has been recorded yet. "
                "Proceed with your task using your own best judgment.\n"
            )

        content = self.memory_file.read_text(encoding="utf-8")

        # Parse entries
        entries = self._parse_entries(content)

        if not entries:
            return (
                "[Team Shared Memory]\n"
                "Shared memory file exists but contains no entries.\n"
            )

        # Sort by timestamp (newest first)
        entries.sort(key=lambda e: e.get("sort_key", ""), reverse=True)

        # Build context
        parts: list[str] = []
        parts.append("[Team Shared Memory — Context for This Execution]")
        parts.append(
            f"({len(entries)} total entries; showing most recent {min(len(entries), max_entries)})\n"
        )

        # Human corrections section (most important)
        human_entries = [e for e in entries if e.get("author", "").startswith("human:")]
        if human_entries:
            parts.append("🔴 HUMAN CORRECTIONS (correct once, all agents learn):")
            for e in human_entries[:5]:
                parts.append(f"  [{e.get('timestamp', '?')}] {e.get('author', '?')}")
                for line in e.get("body", "").strip().split("\n"):
                    parts.append(f"    {line}")
            parts.append("")

        # Recent entries (most recent first)
        parts.append("📋 RECENT TEAM MEMORY:")
        for e in entries[:max_entries]:
            parts.append(f"  [{e.get('timestamp', '?')}] {e.get('author', '?')}")
            for line in e.get("body", "").strip().split("\n"):
                parts.append(f"    {line}")
        parts.append("")

        parts.append(
            "⚠️  IMPORTANT: Before executing, check the memory above for corrections, "
            "constraints, and learnings from previous runs. Apply them to your work."
        )

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _parse_entries(self, content: str) -> list[dict]:
        """Parse SHARED_MEMORY.md content into a list of structured entries."""
        lines = content.split("\n")
        entries: list[dict] = []
        current: Optional[dict] = None

        for line in lines:
            m = ENTRY_HEADER_RE.match(line)
            if m:
                if current is not None:
                    current["body"] = "\n".join(current["_body_lines"])
                    del current["_body_lines"]
                    entries.append(current)
                timestamp = m.group(1)
                author = m.group(2).strip()
                current = {
                    "timestamp": timestamp,
                    "author": author,
                    "sort_key": timestamp,
                    "_body_lines": [],
                }
            elif current is not None:
                current["_body_lines"].append(line)

        if current is not None:
            current["body"] = "\n".join(current["_body_lines"])
            del current["_body_lines"]
            entries.append(current)

        return entries

    # ------------------------------------------------------------------
    # get_all_entries — return all parsed entries as structured dicts
    # ------------------------------------------------------------------
    def get_all_entries(self) -> list[dict]:
        """Return all memory entries as structured dictionaries."""
        if not self.memory_file.exists():
            return []
        return self._parse_entries(self.memory_file.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Seed the shared memory with 3 example entries
# ---------------------------------------------------------------------------
def seed_shared_memory(memory_file: Optional[Path] = None) -> None:
    """Populate SHARED_MEMORY.md with 3 seeded entries demonstrating value."""
    mem = SharedMemory(memory_file)

    # Don't overwrite existing seeded memory
    if mem.memory_file.exists():
        return

    entry1 = (
        "修正：晨报员（ops/morning-brief）在生成每日晨报时，"
        "必须包含当日主要股指数据（上证、深证、恒生、纳斯达克），"
        "而不仅是文字摘要。数据源使用 Yahoo Finance API。"
    )
    entry2 = (
        "修正：所有对外邮件必须使用统一签名模板：\n\n"
        "Best regards,\n"
        "[Name]\n"
        "Moxt.ai Team\n"
        "——\n"
        "邮件首行必须以 \"Hi [Name]\" 开头，"
        "禁止使用 \"Dear\"、\"Hello\"、\"Hey\" 等非规范问候语。"
    )
    entry3 = (
        "已确认：目标客户画像关键词 = [\"SaaS\", \"AI agent\", \"developer tools\", "
        "\"LLM\", \"automation\"]。\n"
        "理想客户规模：10-200 人技术团队。\n"
        "决策者角色：CTO / VP Engineering / Head of AI。\n"
        "排除行业：政府、军工、金融（合规周期过长）。"
    )

    results = [
        mem.write_memory(entry1, author="ops/morning-brief"),
        mem.write_memory(entry2, author="human:CEO"),
        mem.write_memory(entry3, author="sales/cold-outreach"),
    ]

    print(f"✓ Seeded {len(results)} memory entries into {mem.memory_file}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def cmd_show(mem: SharedMemory) -> None:
    content = mem.read_memory()
    if not content.strip():
        print("(shared memory is empty)")
        return
    print(content)


def cmd_add(mem: SharedMemory, entry: str, author: str = "human") -> None:
    result = mem.write_memory(entry, author=author)
    if result["success"]:
        print(f"✓ Memory entry added: {result['header']}")
        print(f"  entry_id: {result['entry_id']}")
    else:
        print(f"✗ Error: {result.get('error', 'unknown')}", file=sys.stderr)
        sys.exit(1)


def cmd_search(mem: SharedMemory, query: str) -> None:
    results = mem.search_memory(query)
    if not results:
        print(f"No results found for: \"{query}\"")
        return
    print(f"Found {len(results)} result(s) for \"{query}\":\n")
    for r in results:
        print(f"  {r['header']}")
        for line in r["body"].strip().split("\n"):
            print(f"    {line}")
        print()


def cmd_context(mem: SharedMemory) -> None:
    ctx = mem.get_team_context()
    print(ctx)


def cmd_correct(mem: SharedMemory, correction_id: str, new_content: str) -> None:
    result = mem.correct_memory(correction_id, new_content)
    if result["success"]:
        print(f"✓ Corrected {result['matched']} entry(ies) matching: \"{correction_id}\"")
    else:
        print(f"✗ Error: {result.get('error', 'unknown')}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hermes Team Shared Memory — correct once, all agents learn",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  hermes-memory.py show
  hermes-memory.py add "竞品监控应包含 GitHub trending"
  hermes-memory.py add --author "human:CEO" "邮件签名必须统一"
  hermes-memory.py search "晨报"
  hermes-memory.py correct "ops/morning-brief" "新的修正内容"
  hermes-memory.py context
""",
    )
    sub = parser.add_subparsers(dest="command", help="Command")

    # show
    sub.add_parser("show", help="Display full shared memory")

    # add
    p_add = sub.add_parser("add", help="Add a correction/learning entry")
    p_add.add_argument("entry", help="The memory entry text")
    p_add.add_argument(
        "--author", "-a",
        default="human",
        help="Author identifier (default: human; e.g. human:CEO, ops/morning-brief)",
    )

    # search
    p_search = sub.add_parser("search", help="Search memory by keyword")
    p_search.add_argument("query", help="Search keyword or phrase")

    # correct
    p_correct = sub.add_parser("correct", help="Update a specific memory entry")
    p_correct.add_argument(
        "correction_id",
        help="Identifier to match the entry (author name, timestamp fragment, etc.)",
    )
    p_correct.add_argument("new_content", help="Replacement body content")

    # context
    sub.add_parser("context", help="Print compressed context for coworker prompt injection")

    # seed (hidden, mainly for internal use)
    sub.add_parser("seed", help="Seed the shared memory with example entries")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    mem = SharedMemory()

    if args.command == "show":
        cmd_show(mem)
    elif args.command == "add":
        cmd_add(mem, args.entry, author=args.author)
    elif args.command == "search":
        cmd_search(mem, args.query)
    elif args.command == "correct":
        cmd_correct(mem, args.correction_id, args.new_content)
    elif args.command == "context":
        cmd_context(mem)
    elif args.command == "seed":
        seed_shared_memory()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
