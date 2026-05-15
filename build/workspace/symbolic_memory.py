#!/usr/bin/env python3
"""
symbolic_memory.py — Phase C: Symbolic Memory Compression (TencentDB distillation).

Compresses verbose tool logs and conversation entries into Mermaid symbol graphs,
reducing token consumption by 30-50% while preserving full traceability via
node_id → raw log drill-down.

Architecture distilled from TencentDB-Agent-Memory (1494★).
Pure Python, zero external dependencies.

Usage:
    from symbolic_memory import SymbolicMemory
    sm = SymbolicMemory()
    graph = sm.compress_session("memory/tiers/l0-conversations/l0-2026-05-15.md")
    print(graph.to_mermaid())
    print(graph.token_stats())
    raw = sm.drill_down("n3")  # retrieve original log for node
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Tool call patterns — recognize common tool invocations in logs
# ---------------------------------------------------------------------------

TOOL_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # (regex, tool_name, icon)
    # ORDER MATTERS: more specific patterns first to avoid overlap
    (re.compile(r"\bweb_search\s*\(\s*[\"'](.+?)[\"']\s*\)"), "web_search", "🔍"),
    (re.compile(r"\bterminal\s*\((.+?)\)", re.DOTALL), "terminal", "💻"),
    (re.compile(r"\bread_file\s*\(\s*[\"'](.+?)[\"']\s*\)"), "read_file", "📄"),
    (re.compile(r"\bwrite_file\s*\(\s*[\"'](.+?)[\"']"), "write_file", "✏️"),
    (re.compile(r"\bpatch\s*\(\s*[\"'](.+?)[\"']"), "patch", "🔧"),
    (re.compile(r"\bbrowser_navigate\s*\(\s*[\"'](.+?)[\"']"), "browser", "🌐"),
    (re.compile(r"\bbrowser_click\b"), "browser_click", "🖱️"),
    (re.compile(r"\bsearch_files\s*\(\s*[\"'](.+?)[\"']"), "search_files", "🔎"),
    (re.compile(r"\bdelegate_task\b"), "delegate_task", "🤖"),
    # git_push must come before generic git
    (re.compile(r"\bgit\s+push\b"), "git_push", "🚀"),
    (re.compile(r"\bgit\s+(commit|add|checkout|merge|rebase)\b"), "git", "📦"),
    (re.compile(r"\bpytest\b"), "test_run", "🧪"),
    (re.compile(r"\bcurl\s+"), "curl", "🌍"),
    (re.compile(r"\bpip\s+install\b"), "pip_install", "📥"),
    (re.compile(r"\bpython\s+\S+\.py\b"), "python_run", "🐍"),
]

# Status indicators
SUCCESS_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bPASSED\b", r"\bOK\b", r"\bsuccess\b",
        r"\bexit[_ ]code.*?0\b", r"\bcommit\s+\w{7}\b",
        r"\ball.*?passed\b", r"\bcompleted\b",
        r"Enumerating objects:.*done", r"main\s*->\s*main",
        r"✓",                      # checkmark (no word boundary needed)
        r"✅",                     # green check emoji
    ]
]

ERROR_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bFAILED\b", r"\bERROR\b", r"\bTraceback\b",
        r"\bexit[_ ]code.*?[1-9]\b", r"\b✗\b", r"\bdenied\b",
        r"\bnot found\b", r"\bModuleNotFoundError\b",
        r"\bPermissionError\b", r"\bConnectionError\b",
        r"\bpanic\b", r"\bfatal\b",
    ]
]


def _make_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


def _make_node_id(prefix: str = "n") -> str:
    """Generate a short unique node ID."""
    return f"{prefix}{hashlib.md5(str(datetime.now(timezone.utc).timestamp()).encode()).hexdigest()[:6]}"


def _truncate(text: str, max_lines: int = 3, max_chars: int = 200) -> str:
    """Truncate verbose output to a summary."""
    lines = text.strip().split("\n")
    if len(lines) <= max_lines and len(text) <= max_chars:
        return text
    truncated = "\n".join(lines[:max_lines])
    if len(truncated) > max_chars:
        truncated = truncated[:max_chars - 3] + "..."
    remaining = len(lines) - max_lines
    if remaining > 0:
        truncated += f"\n  ... (+{remaining} lines)"
    return truncated


def _detect_status(text: str) -> str:
    """Detect success/error/neutral status from tool output."""
    for pat in ERROR_PATTERNS:
        if pat.search(text):
            return "error"
    for pat in SUCCESS_PATTERNS:
        if pat.search(text):
            return "success"
    return "neutral"


def _extract_tool_calls(text: str) -> list[dict]:
    """Extract tool call signatures from conversation text.

    Avoids double-counting: if a pattern matches inside another
    tool call's argument (e.g. 'terminal('git push')' → only terminal
    is counted, not the inner git push).
    """
    raw_calls: list[dict] = []

    for pattern, tool_name, icon in TOOL_PATTERNS:
        for m in pattern.finditer(text):
            arg = m.group(1).strip() if m.lastindex and m.lastindex >= 1 else ""
            # Strip surrounding quotes from terminal-like args
            arg = arg.strip("'\"")
            if len(arg) > 80:
                arg = arg[:77] + "..."
            raw_calls.append({
                "tool": tool_name,
                "icon": icon,
                "arg": arg,
                "start": m.start(),
                "end": m.end(),
                "full_match": m.group(0),
            })

    # Sort by start position
    raw_calls.sort(key=lambda c: c["start"])

    # Filter: skip matches that fall inside an earlier match's span
    # (e.g. 'terminal('git push')' → keep terminal, drop git_push)
    calls: list[dict] = []
    accepted_spans: list[tuple[int, int]] = []

    for call in raw_calls:
        start, end = call["start"], call["end"]
        # Check if this span is contained within any accepted span
        contained = any(
            acc_start <= start and end <= acc_end
            for acc_start, acc_end in accepted_spans
        )
        if not contained:
            calls.append(call)
            accepted_spans.append((start, end))

    return calls


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SymbolNode:
    """A single node in the Mermaid symbol graph."""
    node_id: str
    tool: str
    icon: str
    label: str
    summary: str = ""
    status: str = "neutral"  # success | error | neutral
    raw_log: str = ""        # original text this node represents
    children: list[str] = field(default_factory=list)  # node_ids of next steps


@dataclass
class SymbolGraph:
    """A Mermaid flowchart representing a compressed session."""
    session_id: str
    nodes: list[SymbolNode]
    raw_total_chars: int
    compressed_chars: int
    created_at: str = field(default_factory=_make_timestamp)

    def to_mermaid(self, direction: str = "TD") -> str:
        """Render the graph as a Mermaid flowchart string."""
        if not self.nodes:
            return "flowchart TD\n    empty[\"📭 No tool calls in session\"]"

        lines = [f"flowchart {direction}"]
        lines.append("")

        # Node definitions
        for node in self.nodes:
            status_suffix = ""
            if node.status == "success":
                status_suffix = " ✅"
            elif node.status == "error":
                status_suffix = " ❌"
            label = f"{node.icon} {node.tool}"
            if node.label:
                label += f": {node.label}"
            label += status_suffix

            # Escape quotes in label for Mermaid
            safe_label = label.replace('"', "'")
            lines.append(f"    {node.node_id}[\"{safe_label}\"]")

        lines.append("")

        # Edges
        for i, node in enumerate(self.nodes):
            if node.children:
                for child_id in node.children:
                    lines.append(f"    {node.node_id} --> {child_id}")
            elif i < len(self.nodes) - 1:
                # Default sequential flow
                lines.append(f"    {node.node_id} --> {self.nodes[i + 1].node_id}")

        return "\n".join(lines)

    def to_summary_text(self) -> str:
        """Return a compressed text summary suitable for prompt injection."""
        if not self.nodes:
            return "[Symbolic Memory] Session has no tool calls."

        tool_counts: dict[str, int] = {}
        success_count = 0
        error_count = 0

        for node in self.nodes:
            tool_counts[node.tool] = tool_counts.get(node.tool, 0) + 1
            if node.status == "success":
                success_count += 1
            elif node.status == "error":
                error_count += 1

        parts = ["[Symbolic Memory — Compressed Session Summary]"]
        parts.append(f"Tool calls: {len(self.nodes)} ({success_count}✅ {error_count}❌)")

        if tool_counts:
            parts.append("Tools used: " + ", ".join(
                f"{icon}{tool}×{count}"
                for tool, count in sorted(tool_counts.items(), key=lambda x: -x[1])
                for _, icon, _ in [(p[1], p[2], p[0]) for p in TOOL_PATTERNS if p[1] == tool]
            ))

        parts.append("")
        for node in self.nodes:
            status_icon = "✅" if node.status == "success" else ("❌" if node.status == "error" else "➡️")
            parts.append(f"  {status_icon} {node.node_id}: {node.icon} {node.tool} → {node.summary}")

        parts.append("")
        parts.append(f"Compression: {self.raw_total_chars}→{self.compressed_chars} chars "
                      f"({self.compression_ratio():.0%} savings)")

        return "\n".join(parts)

    def compression_ratio(self) -> float:
        """Return compression ratio (0.0 = no savings, 0.5 = 50% saved)."""
        if self.raw_total_chars == 0:
            return 0.0
        return 1.0 - (self.compressed_chars / self.raw_total_chars)

    def token_stats(self) -> dict:
        """Return token consumption statistics."""
        # Rough estimate: 1 token ≈ 4 chars
        raw_tokens = self.raw_total_chars // 4
        compressed_tokens = self.compressed_chars // 4
        return {
            "raw_chars": self.raw_total_chars,
            "compressed_chars": self.compressed_chars,
            "raw_tokens_est": raw_tokens,
            "compressed_tokens_est": compressed_tokens,
            "savings_tokens_est": raw_tokens - compressed_tokens,
            "compression_ratio": self.compression_ratio(),
        }


# ---------------------------------------------------------------------------
# SymbolicMemory — main compression engine
# ---------------------------------------------------------------------------

class SymbolicMemory:
    """Compress verbose tool logs into Mermaid symbol graphs.

    Key features:
    - Parse tool call sequences from L0 conversation logs
    - Compress verbose outputs to one-line summaries
    - Detect success/error status for visual indicators
    - Maintain full traceability via node_id → raw log drill-down
    - Target: 30-50% token savings on tool-heavy sessions
    """

    def __init__(self, index_file: Optional[Path] = None):
        """Initialize with optional node index persistence.

        The node index maps node_id → raw log content for drill-down.
        If index_file is provided, the index is persisted to disk.
        """
        self._index: dict[str, str] = {}  # node_id → raw log text
        self._index_file = index_file
        if index_file and index_file.exists():
            try:
                self._index = json.loads(index_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._index = {}

    # ── L0 parsing ────────────────────────────────────────────────

    def parse_session(self, content: str) -> list[SymbolNode]:
        """Parse an L0 conversation and extract tool call nodes.

        Returns a list of SymbolNode in chronological order.
        """
        # Split into entries (## [...] author blocks)
        entries = re.split(r"\n(?=## \[)", content)
        nodes: list[SymbolNode] = []

        for entry in entries:
            if not entry.strip():
                continue

            # Extract tool calls from this entry
            calls = _extract_tool_calls(entry)
            if not calls:
                # Entry has no tool calls — skip (it's a human message or narrative)
                continue

            # Determine status from the entry text
            status = _detect_status(entry)

            # Create a node for each tool call
            for call in calls:
                node_id = _make_node_id()
                summary = call["arg"] if call["arg"] else call["tool"]

                node = SymbolNode(
                    node_id=node_id,
                    tool=call["tool"],
                    icon=call["icon"],
                    label=call["arg"][:60] if call["arg"] else "",
                    summary=_truncate(summary, max_lines=1, max_chars=100),
                    status=status,
                    raw_log=_truncate(entry.strip(), max_lines=50, max_chars=2000),
                )
                nodes.append(node)

                # Store raw log in index for drill-down
                self._index[node_id] = entry.strip()

        return nodes

    # ── Compression ────────────────────────────────────────────────

    def compress_session(
        self,
        session_path: Optional[Path] = None,
        session_text: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> SymbolGraph:
        """Compress a session into a SymbolGraph.

        Provide either session_path (reads file) or session_text (direct string).

        Returns a SymbolGraph with Mermaid-ready nodes and token stats.
        """
        if session_path:
            content = session_path.read_text(encoding="utf-8")
            sid = session_path.stem
        elif session_text:
            content = session_text
            sid = session_id or "inline"
        else:
            raise ValueError("Provide session_path or session_text")

        raw_chars = len(content)
        nodes = self.parse_session(content)

        # Compress: each node's summary is the compressed representation
        compressed_chars = sum(
            len(node.summary) + len(node.tool) + 10  # ~10 chars overhead per node
            for node in nodes
        )

        # If no tool calls found, the session is already "compressed"
        if not nodes:
            compressed_chars = min(raw_chars, 500)

        return SymbolGraph(
            session_id=sid,
            nodes=nodes,
            raw_total_chars=raw_chars,
            compressed_chars=compressed_chars,
        )

    # ── Drill-down ─────────────────────────────────────────────────

    def drill_down(self, node_id: str) -> Optional[str]:
        """Retrieve the raw log text for a given node_id.

        Returns None if the node_id is not found in the index.
        """
        return self._index.get(node_id)

    def get_node_ids(self) -> list[str]:
        """List all indexed node IDs."""
        return list(self._index.keys())

    def save_index(self) -> None:
        """Persist the node index to disk (if index_file was provided at init)."""
        if self._index_file:
            self._index_file.parent.mkdir(parents=True, exist_ok=True)
            self._index_file.write_text(
                json.dumps(self._index, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    # ── Statistics ─────────────────────────────────────────────────

    def compression_stats(self, session_path: Path) -> dict:
        """Get compression statistics for a session file."""
        content = session_path.read_text(encoding="utf-8")
        graph = self.compress_session(session_text=content, session_id=session_path.stem)
        stats = graph.token_stats()
        stats["session_id"] = session_path.stem
        stats["node_count"] = len(graph.nodes)
        return stats


# ---------------------------------------------------------------------------
# Integration helper — add to SharedMemory
# ---------------------------------------------------------------------------

def symbolic_compress_l0_session(
    l0_path: Path,
    index_file: Optional[Path] = None,
) -> SymbolGraph:
    """Convenience function to compress an L0 session file.

    Usage from SharedMemory:
        from symbolic_memory import symbolic_compress_l0_session
        graph = symbolic_compress_l0_session(Path("memory/tiers/l0-conversations/l0-2026-05-15.md"))
        print(graph.to_mermaid())
    """
    sm = SymbolicMemory(index_file=index_file)
    return sm.compress_session(session_path=l0_path)
