#!/usr/bin/env python3
"""
hermes-memory.py v2.0 — 4-Tier Memory Layer (TencentDB Architecture Distillation).

v2.0 新增:
  - 4-tier pipeline: L0 Conversation → L1 Atom → L2 Scenario → L3 Persona
  - write_to_tier() / get_tier_entries() / get_tiered_context()
  - migrate_from_flat() — 将扁平 SHARED_MEMORY.md 迁移为分层结构
  - 渐进披露：默认注入 L3，需要时 drill-down
  - 零外部依赖，纯 Python

Architecture distilled from TencentDB-Agent-Memory (1494★).
See: docs/architecture/memory-v2-tencentdb-distillation.md

Changelog from v1.2:
  - SharedMemory 保留所有 v1.2 API（向后兼容）
  - 新增 4-tier 目录结构和读写方法
  - get_team_context() 改为渐进披露模式
  - 新增 migrate_from_flat() 迁移工具
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
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
NAMESPACES_DIR = PROJECT_ROOT / "memory" / "namespaces"

# v2.0 — 4-tier directory structure
MEMORY_TIERS_DIR = PROJECT_ROOT / "memory" / "tiers"
TIER_DIRS = {
    "l0": MEMORY_TIERS_DIR / "l0-conversations",
    "l1": MEMORY_TIERS_DIR / "l1-atoms",
    "l2": MEMORY_TIERS_DIR / "l2-scenarios",
    "l3": MEMORY_TIERS_DIR / "l3-personas",
}

TIER_META = {
    "l0": {"name": "Conversation", "desc": "原始对话记录 — 证据源，不可丢失", "format": "md"},
    "l1": {"name": "Atom", "desc": "原子事实 — 去重提取，快速检索", "format": "jsonl"},
    "l2": {"name": "Scenario", "desc": "场景块 — 上下文模式，SOP模板", "format": "md"},
    "l3": {"name": "Persona", "desc": "用户画像 — 长期偏好，少样本注入", "format": "md"},
}

# ---------------------------------------------------------------------------
# Entry format helpers
# ---------------------------------------------------------------------------
ENTRY_HEADER_RE = re.compile(
    r"^##\s+\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\]\s+(.+?)\s*$"
)

# Valid namespaces and their access rules
VALID_NAMESPACES = {
    "shared": {"access": "team", "retention_days": None, "desc": "团队共享记忆 — 所有同事可读写"},
    "personal": {"access": "owner", "retention_days": 90, "desc": "个人记忆 — 仅所有者可读写"},
    "board": {"access": "board", "retention_days": None, "desc": "板块记忆 — 同一板块成员可读写"},
    "audit": {"access": "governance", "retention_days": 365, "desc": "审计日志 — 治理层只读"},
}


def _make_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


def _make_entry_id() -> str:
    return uuid.uuid4().hex[:8]


def _compute_audit_hash(entry: str, author: str, timestamp: str) -> str:
    """Compute a deterministic hash for audit/governance tracking."""
    payload = f"{timestamp}|{author}|{entry}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# SharedMemory — the importable Python API
# ---------------------------------------------------------------------------
class SharedMemory:
    """Team shared memory layer backed by SHARED_MEMORY.md with namespace support."""

    def __init__(
        self,
        memory_file: Optional[Path] = None,
        namespace: str = "shared",
    ):
        self.memory_file = Path(memory_file) if memory_file else DEFAULT_MEMORY_FILE
        self.namespace = namespace
        self._namespace_dir = NAMESPACES_DIR

    # ── Namespace support ────────────────────────────────────────

    def list_namespaces(self) -> list[dict]:
        """List available namespaces and their metadata."""
        return [
            {"id": ns_id, **meta}
            for ns_id, meta in VALID_NAMESPACES.items()
        ]

    def get_namespace_entries(self, namespace: str) -> list[dict]:
        """Get entries for a specific namespace."""
        ns_file = self._namespace_dir / f"{namespace}.md"
        if not ns_file.exists():
            return []
        content = ns_file.read_text(encoding="utf-8")
        return self._parse_entries(content)

    def write_to_namespace(
        self,
        entry: str,
        author: str = "unknown",
        namespace: str = "shared",
        access_level: str = "read-write",
    ) -> dict:
        """Write a memory entry to a specific namespace."""
        if namespace not in VALID_NAMESPACES:
            return {"success": False, "error": f"Unknown namespace: {namespace}"}

        entry_id = _make_entry_id()
        timestamp = _make_timestamp()
        audit_hash = _compute_audit_hash(entry, author, timestamp)

        ns_file = self._namespace_dir / f"{namespace}.md"
        ns_file.parent.mkdir(parents=True, exist_ok=True)

        # Write metadata as JSON comment, then the markdown entry
        metadata = json.dumps({
            "entry_id": entry_id,
            "namespace": namespace,
            "access_level": access_level,
            "retention_days": VALID_NAMESPACES[namespace]["retention_days"],
            "audit_hash": audit_hash,
        })

        if not ns_file.exists():
            ns_file.write_text(
                f"# {namespace.capitalize()} Memory\n\n"
                f"> Namespace: {namespace} | Access: {VALID_NAMESPACES[namespace]['access']}\n\n",
                encoding="utf-8",
            )

        header = f"## [{timestamp}] {author}"
        body = entry.strip()
        entry_block = (
            f"<!-- {metadata} -->\n"
            f"{header}\n"
            f"{body}\n\n"
        )

        with open(ns_file, "a", encoding="utf-8") as f:
            f.write("\n" + entry_block)

        return {
            "success": True,
            "entry_id": entry_id,
            "namespace": namespace,
            "author": author,
            "timestamp": timestamp,
            "audit_hash": audit_hash,
        }

    # ── v2.0 — 4-Tier Memory Methods ───────────────────────────────

    def _ensure_tier_dirs(self):
        """Create all tier directories if they don't exist."""
        for tier, dir_path in TIER_DIRS.items():
            dir_path.mkdir(parents=True, exist_ok=True)
            # Create a README in each tier
            readme = dir_path / "README.md"
            if not readme.exists():
                meta = TIER_META[tier]
                readme.write_text(
                    f"# {meta['name']} Tier (L{tier[-1]})\n\n"
                    f"> {meta['desc']}\n\n"
                    f"Format: {meta['format']}\n\n"
                    f"---\n\n",
                    encoding="utf-8",
                )

    def write_to_tier(
        self,
        tier: str,
        entry: str,
        author: str = "unknown",
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Write an entry to a specific memory tier.

        Tiers:
          l0 — raw conversation logs (append-only .md)
          l1 — atomic facts (jsonl, one JSON object per line)
          l2 — scenario blocks (structured .md with metadata header)
          l3 — persona profiles (structured .md with metadata header)
        """
        if tier not in TIER_DIRS:
            return {"success": False, "error": f"Unknown tier: {tier}. Use l0/l1/l2/l3."}

        self._ensure_tier_dirs()
        tier_dir = TIER_DIRS[tier]
        entry_id = _make_entry_id()
        timestamp = _make_timestamp()
        meta = metadata or {}

        if tier == "l1":
            # JSONL format — one atomic fact per line
            atom_file = tier_dir / f"atoms-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
            atom = json.dumps({
                "id": entry_id,
                "timestamp": timestamp,
                "author": author,
                "fact": entry.strip(),
                **meta,
            }, ensure_ascii=False)
            with open(atom_file, "a", encoding="utf-8") as f:
                f.write(atom + "\n")
            return {
                "success": True, "entry_id": entry_id, "tier": tier,
                "author": author, "timestamp": timestamp,
            }

        elif tier in ("l0", "l2", "l3"):
            # Markdown format
            file_name = f"{tier}-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
            tier_file = tier_dir / file_name
            header = f"## [{timestamp}] {author}"
            meta_block = f"<!-- {json.dumps({'id': entry_id, 'tier': tier, **meta})} -->\n"
            block = f"{meta_block}{header}\n{entry.strip()}\n\n"
            with open(tier_file, "a", encoding="utf-8") as f:
                f.write("\n" + block)
            return {
                "success": True, "entry_id": entry_id, "tier": tier,
                "author": author, "timestamp": timestamp,
            }

        return {"success": False, "error": f"Unsupported tier format: {tier}"}

    def get_tier_entries(self, tier: str, limit: int = 50) -> list[dict]:
        """
        Retrieve entries from a specific tier.

        l0/l2/l3: returns parsed markdown entries
        l1: returns atom dicts from jsonl files

        Results sorted newest-first.
        """
        if tier not in TIER_DIRS:
            return []

        tier_dir = TIER_DIRS[tier]
        if not tier_dir.exists():
            return []

        if tier == "l1":
            entries = []
            for jsonl_file in sorted(tier_dir.glob("atoms-*.jsonl"), reverse=True):
                try:
                    for line in jsonl_file.read_text(encoding="utf-8").strip().split("\n"):
                        if line.strip():
                            entries.append(json.loads(line))
                except (json.JSONDecodeError, OSError):
                    continue
            return entries[:limit]

        elif tier in ("l0", "l2", "l3"):
            all_entries = []
            for md_file in sorted(tier_dir.glob(f"{tier}-*.md"), reverse=True):
                try:
                    content = md_file.read_text(encoding="utf-8")
                    parsed = self._parse_entries(content)
                    for e in parsed:
                        e["_tier"] = tier
                        e["_source_file"] = str(md_file.name)
                    all_entries.extend(parsed)
                except OSError:
                    continue
            return all_entries[:limit]

        return []

    def get_tiered_context(self) -> str:
        """
        Progressive disclosure context for AI agent prompt injection.

        Prioritizes:
        1. L3 Persona (highest signal, always injected)
        2. L2 Scenario (if relevant to current task)
        3. L0/L1 (summary only — drill-down via entry_id)
        """
        self._ensure_tier_dirs()
        parts = ["[Hermes Memory v2 — 4-Tier Progressive Context]\n"]

        # L3 — Persona (always injected, high signal)
        l3_entries = self.get_tier_entries("l3", limit=5)
        if l3_entries:
            parts.append("## 🧠 L3 Persona — 长期偏好与画像")
            for e in l3_entries:
                author = e.get("author", "?")
                body = e.get("body", "").strip()
                parts.append(f"  [{e.get('timestamp', '?')}] {author}")
                for line in body.split("\n")[:10]:
                    parts.append(f"    {line}")
            parts.append("")

        # L2 — Scenario (recent context patterns)
        l2_entries = self.get_tier_entries("l2", limit=3)
        if l2_entries:
            parts.append("## 📋 L2 Scenario — 上下文模式与 SOP")
            for e in l2_entries:
                author = e.get("author", "?")
                body = e.get("body", "").strip()
                parts.append(f"  [{e.get('timestamp', '?')}] {author}")
                for line in body.split("\n")[:8]:
                    parts.append(f"    {line}")
            parts.append("")

        # L1 — Atom summary (count only, details on demand)
        l1_count = len(self.get_tier_entries("l1", limit=1000))
        l0_count = len(self.get_tier_entries("l0", limit=1000))
        if l1_count or l0_count:
            parts.append(f"📊 L1 Atoms: {l1_count} facts | L0 Conversations: {l0_count} sessions")
            parts.append("   (use search_memory() or get_tier_entries() for drill-down)")
            parts.append("")

        # Fall back to flat memory if tiers are empty and flat exists
        if not l3_entries and not l2_entries and self.memory_file.exists():
            parts.append("---")
            parts.append("(4-tier memory is empty — showing legacy flat memory)")
            return "\n".join(parts) + "\n" + self.get_team_context()

        parts.append("⚠️  Check L3 Persona for user preferences before executing.")
        parts.append("    Drill down with get_tier_entries('l1') for specific facts.")
        return "\n".join(parts)

    def migrate_from_flat(self) -> dict:
        """
        Migrate entries from flat SHARED_MEMORY.md into the 4-tier structure.

        Heuristic:
        - Human corrections → L3 Persona
        - Agent corrections/learnings → L2 Scenario
        - Everything else → L0 Conversation (preserve original)
        """
        self._ensure_tier_dirs()
        if not self.memory_file.exists():
            return {"success": False, "error": "Flat memory file not found"}

        entries = self.get_all_entries()
        stats = {"l0": 0, "l2": 0, "l3": 0, "total": len(entries)}

        for e in entries:
            author = e.get("author", "")
            body = e.get("body", "").strip()
            timestamp = e.get("timestamp", "")

            if author.startswith("human:") or "CEO" in author:
                tier = "l3"
            elif "修正" in body or "correct" in body.lower() or "learn" in body.lower():
                tier = "l2"
            else:
                tier = "l0"

            self.write_to_tier(
                tier=tier,
                entry=body,
                author=author,
                metadata={"migrated_from": "flat", "original_ts": timestamp},
            )
            stats[tier] += 1

        return {"success": True, "migrated": stats["total"], "by_tier": stats}

    def list_tiers(self) -> list[dict]:
        """List all tiers and their entry counts."""
        self._ensure_tier_dirs()
        result = []
        for tier_id in ["l0", "l1", "l2", "l3"]:
            entries = self.get_tier_entries(tier_id, limit=10000)
            result.append({
                "id": tier_id,
                "name": TIER_META[tier_id]["name"],
                "desc": TIER_META[tier_id]["desc"],
                "format": TIER_META[tier_id]["format"],
                "entry_count": len(entries),
                "dir": str(TIER_DIRS[tier_id]),
            })
        return result

    # ── Phase C — Symbolic Memory Compression ───────────────────────

    def compress_session(
        self,
        l0_path: Optional[Path] = None,
        l0_text: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> dict:
        """Compress an L0 session into a Mermaid symbol graph.

        Phase C of Memory v2 (TencentDB architecture).
        Reduces token consumption by 30-50% on tool-heavy sessions.

        Returns dict with:
          - mermaid: Mermaid flowchart string
          - summary_text: compressed text summary
          - token_stats: raw vs compressed token estimates
          - node_ids: list of node IDs for drill-down
        """
        try:
            from symbolic_memory import SymbolicMemory
        except ImportError:
            return {"success": False, "error": "symbolic_memory module not found"}

        sm = SymbolicMemory()
        graph = sm.compress_session(
            session_path=l0_path,
            session_text=l0_text,
            session_id=session_id,
        )

        return {
            "success": True,
            "mermaid": graph.to_mermaid(),
            "summary_text": graph.to_summary_text(),
            "token_stats": graph.token_stats(),
            "node_ids": [n.node_id for n in graph.nodes],
            "node_count": len(graph.nodes),
            "compression_ratio": graph.compression_ratio(),
        }

    # ── GateMem compatibility ────────────────────────────────────

    def gate_mem_compat_export(self) -> dict:
        """
        Export memory in GateMem-compatible format for benchmarking.

        GateMem (rzhub/GateMem) is a benchmark for memory governance in
        multi-principal shared-memory LLM agents. This export produces
        a JSON structure that GateMem's evaluation toolkit can consume.
        """
        principals = {}
        for ns_id in VALID_NAMESPACES:
            entries = self.get_namespace_entries(ns_id)
            if entries:
                principals[ns_id] = {
                    "principal_type": VALID_NAMESPACES[ns_id]["access"],
                    "entry_count": len(entries),
                    "entries": [
                        {
                            "timestamp": e.get("timestamp"),
                            "author": e.get("author"),
                            "body": e.get("body", "")[:200],
                        }
                        for e in entries[-20:]  # Last 20 for benchmark
                    ],
                }

        return {
            "format": "gate-mem-v1",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "total_entries": sum(
                len(p["entries"]) for p in principals.values()
            ),
            "principals": principals,
        }

    # ── Original methods (from v1.0/v1.1) ────────────────────────

    def read_memory(self, scope: str = "shared") -> str:
        if not self.memory_file.exists():
            return ""
        return self.memory_file.read_text(encoding="utf-8")

    def write_memory(
        self, entry: str, author: str = "unknown", scope: str = "shared"
    ) -> dict:
        entry_id = _make_entry_id()
        timestamp = _make_timestamp()
        header = f"## [{timestamp}] {author}"
        body_lines = [line for line in entry.strip().split("\n")]
        entry_block = header + "\n" + "\n".join(body_lines) + "\n"

        if not self.memory_file.exists():
            self.memory_file.parent.mkdir(parents=True, exist_ok=True)
            self.memory_file.write_text(
                "# Team Shared Memory\n\n"
                "> 纠正一个 Agent 犯的错，团队里所有 Agent 都记住了。\n"
                "> Correct one agent's mistake, ALL agents remember it.\n\n",
                encoding="utf-8",
            )

        with open(self.memory_file, "a", encoding="utf-8") as f:
            f.write("\n" + entry_block)

        return {
            "success": True,
            "entry_id": entry_id,
            "header": header,
            "author": author,
            "timestamp": timestamp,
        }

    def correct_memory(self, correction_id: str, new_content: str) -> dict:
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
                if in_target:
                    new_lines.append(header_line)
                    for body_line in new_content.strip().split("\n"):
                        new_lines.append(body_line)
                    in_target = False

                full_date_author = f"[{m.group(1)}] {m.group(2)}"
                if (
                    correction_id in line
                    or correction_id in full_date_author
                    or correction_id in m.group(2)
                ):
                    in_target = True
                    header_line = line
                    matched += 1
                    continue

            if not in_target:
                new_lines.append(line)

        if in_target:
            new_lines.append(header_line)
            for body_line in new_content.strip().split("\n"):
                new_lines.append(body_line)

        if matched == 0:
            return {"success": False, "error": "No matching entry found", "matched": 0}

        self.memory_file.write_text("\n".join(new_lines), encoding="utf-8")
        return {"success": True, "matched": matched}

    def search_memory(self, query: str) -> list[dict]:
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
                if current_header is not None:
                    body_text = "\n".join(current_body_lines)
                    if query_lower in current_header.lower() or query_lower in body_text.lower():
                        results.append({
                            "header": current_header.strip().lstrip("#").strip(),
                            "body": body_text,
                            "line_start": current_start,
                            "line_end": i - 1,
                        })
                current_header = line
                current_body_lines = []
                current_start = i
            else:
                current_body_lines.append(line)

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

    def get_team_context(self, max_entries: int = 20) -> str:
        if not self.memory_file.exists():
            return (
                "[Team Shared Memory]\n"
                "No shared memory has been recorded yet. "
                "Proceed with your task using your own best judgment.\n"
            )
        content = self.memory_file.read_text(encoding="utf-8")
        entries = self._parse_entries(content)
        if not entries:
            return (
                "[Team Shared Memory]\n"
                "Shared memory file exists but contains no entries.\n"
            )
        entries.sort(key=lambda e: e.get("sort_key", ""), reverse=True)
        parts: list[str] = []
        parts.append("[Team Shared Memory — Context for This Execution]")
        parts.append(
            f"({len(entries)} total entries; showing most recent {min(len(entries), max_entries)})\n"
        )
        human_entries = [e for e in entries if e.get("author", "").startswith("human:")]
        if human_entries:
            parts.append("🔴 HUMAN CORRECTIONS (correct once, all agents learn):")
            for e in human_entries[:5]:
                parts.append(f"  [{e.get('timestamp', '?')}] {e.get('author', '?')}")
                for line in e.get("body", "").strip().split("\n"):
                    parts.append(f"    {line}")
            parts.append("")
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

    def _parse_entries(self, content: str) -> list[dict]:
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

    def get_all_entries(self) -> list[dict]:
        if not self.memory_file.exists():
            return []
        return self._parse_entries(self.memory_file.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Phase B — Distillation Pipeline (L0 → L1 → L2 → L3)
# Architecture distilled from TencentDB-Agent-Memory (1494★).
# Pure Python, zero external deps. Heuristic extraction for offline use;
# plug in LLM-based extraction via extract_facts_llm() for production.
# ---------------------------------------------------------------------------

# ── Fact extraction patterns (heuristic) ─────────────────────────

FACT_PATTERNS: list[tuple[re.Pattern, str]] = [
    # (pattern, fact_type)
    (re.compile(r"修正[:：](.+)"), "correction"),
    (re.compile(r"(?:必须|禁止|不允许|不应|切勿)(.+)"), "constraint"),
    (re.compile(r"偏好|prefer(?:ence)?|喜欢|习惯[:：]?\s*(.+)", re.IGNORECASE), "preference"),
    (re.compile(r"(?:已确认|确认|决定|定调)[:：](.+)"), "decision"),
    (re.compile(r"(?:目标|定位|策略)[:：]\s*(.+)"), "strategy"),
    (re.compile(r"https?://[^\s)\]]+"), "url"),
    (re.compile(r"(?:/~)?[/\w.-]+/[\w.-]+\.(?:py|md|json|yml|yaml|toml|sh|ts|js|tsx|jsx)\b"), "file_path"),
    (re.compile(r"(?:agent|bot|team|board|pipeline)[_.-]?\w+\s+(?:is|现在|currently)\s+(.+)", re.IGNORECASE), "state"),
    (re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:★|star|commit|PR|issue|hour|day|week|month)\b", re.IGNORECASE), "metric"),
    (re.compile(r"[""「](.+?)[""」](?:很重要|是关键|需要注意|必须记住)"), "quote_key"),
    (re.compile(r"记住[:：]\s*(.+)"), "reminder"),
]


def _extract_facts_from_text(text: str, source_id: str = "") -> list[dict]:
    """Extract atomic facts from a text block using heuristic patterns.

    Returns list of {type, text, source, confidence} dicts.
    """
    facts: list[dict] = []
    seen_spans: set[tuple[int, int]] = set()

    for pattern, fact_type in FACT_PATTERNS:
        for m in pattern.finditer(text):
            span = (m.start(), m.end())
            if span in seen_spans:
                continue
            seen_spans.add(span)
            fact_text = m.group(0).strip()
            # For patterns with capture groups, use the captured content as the fact
            if m.lastindex and m.lastindex >= 1:
                for g in range(1, m.lastindex + 1):
                    if m.group(g):
                        fact_text = m.group(g).strip()
                        break
            # Assign confidence: explicit patterns → higher confidence
            confidence = {
                "correction": 0.90,
                "constraint": 0.92,
                "preference": 0.85,
                "decision": 0.88,
                "strategy": 0.80,
                "reminder": 0.87,
                "url": 0.95,
                "file_path": 0.75,
                "state": 0.60,
                "metric": 0.65,
                "quote_key": 0.70,
            }.get(fact_type, 0.50)

            facts.append({
                "type": fact_type,
                "text": fact_text,
                "source": source_id,
                "confidence": confidence,
            })

    return facts


def _keyword_overlap(a: dict, b: dict) -> int:
    """Count shared significant keywords between two atoms.

    Handles CJK characters (2+ chars) and ASCII words (3+ chars).
    """
    stop_words = {"the", "and", "for", "from", "with", "this", "that",
                   "have", "been", "was", "are", "has", "not", "but",
                   "can", "all", "will", "just", "now", "its", "also",
                   "了", "的", "是", "在", "有", "和", "不", "也", "都", "就",
                   "要", "会", "可", "以", "及", "或", "被", "让", "把", "对",
                   "而", "与", "但", "因", "所", "为", "从", "到", "等",
                   "一个", "我们", "他们", "你们", "它们", "这个", "那个",
                   "已经", "可以", "没有", "什么", "自己", "知道", "如果"}

    def _extract_words(text: str) -> set[str]:
        words: set[str] = set()
        # ASCII words (3+ chars)
        for w in re.findall(r"\w{3,}", text):
            if w.lower() not in stop_words:
                words.add(w.lower())
        # CJK bigrams (2 consecutive Chinese chars)
        cjk_chars = re.findall(r"[\u4e00-\u9fff]", text)
        for i in range(len(cjk_chars) - 1):
            bigram = cjk_chars[i] + cjk_chars[i + 1]
            if bigram not in stop_words:
                words.add(bigram)
        return words

    words_a = _extract_words(a.get("fact", a.get("text", "")))
    words_b = _extract_words(b.get("fact", b.get("text", "")))
    return len(words_a & words_b)


def _cluster_atoms(atoms: list[dict], min_overlap: int = 2) -> list[list[dict]]:
    """Simple greedy clustering of atoms by keyword overlap."""
    if not atoms:
        return []
    clusters: list[list[dict]] = []
    remaining = list(atoms)
    while remaining:
        seed = remaining.pop(0)
        cluster = [seed]
        i = 0
        while i < len(remaining):
            if _keyword_overlap(seed, remaining[i]) >= min_overlap:
                cluster.append(remaining.pop(i))
            else:
                i += 1
        clusters.append(cluster)
    return clusters


# ── DistillationPipeline ──────────────────────────────────────────

class DistillationPipeline:
    """Automatic memory distillation: L0→L1→L2→L3.

    Phase B of Memory v2 (TencentDB architecture distillation).
    Works with the existing SharedMemory tier storage.

    Usage:
        mem = SharedMemory()
        pipe = DistillationPipeline(mem)
        result = pipe.auto_distill()  # run full pipeline
        status = pipe.get_status()    # check what needs processing
    """

    def __init__(self, memory: SharedMemory):
        self.mem = memory
        self.mem._ensure_tier_dirs()
        self._processed_l0: set[str] = set()   # track processed L0 file paths
        self._processed_l1_atoms: set[str] = set()  # track processed atom IDs

    # ── L0 → L1: Extract facts from raw conversations ─────────────

    def distill_l0_to_l1(self) -> dict:
        """Extract atomic facts from all L0 conversation files.

        Processes each L0 .md file, runs heuristic fact extraction,
        and writes discovered facts to L1 jsonl. Tracks which L0 files
        have been processed to avoid re-extraction.
        """
        l0_dir = TIER_DIRS["l0"]
        if not l0_dir.exists():
            return {"success": True, "facts_extracted": 0, "sources_processed": 0,
                    "message": "L0 directory is empty — nothing to distill"}

        total_facts = 0
        files_processed = 0

        for md_file in sorted(l0_dir.glob("l0-*.md")):
            if str(md_file) in self._processed_l0:
                continue

            try:
                content = md_file.read_text(encoding="utf-8")
            except OSError:
                continue

            # Extract per-entry facts (each entry may have its own context)
            entries = self.mem._parse_entries(content)
            for entry in entries:
                body = entry.get("body", "")
                author = entry.get("author", "")
                facts = _extract_facts_from_text(body, source_id=str(md_file.name))
                for fact in facts:
                    self.mem.write_to_tier(
                        tier="l1",
                        entry=fact["text"],
                        author=author,
                        metadata={
                            "fact_type": fact["type"],
                            "confidence": fact["confidence"],
                            "source_l0": str(md_file.name),
                            "source_author": author,
                        },
                    )
                total_facts += len(facts)

            self._processed_l0.add(str(md_file))
            files_processed += 1

        return {
            "success": True,
            "facts_extracted": total_facts,
            "sources_processed": files_processed,
            "message": f"Extracted {total_facts} facts from {files_processed} L0 sources",
        }

    # ── L1 → L2: Cluster atoms into scenario blocks ────────────────

    def distill_l1_to_l2(self, max_atoms: int = 200) -> dict:
        """Cluster L1 atoms into L2 scenario blocks.

        Reads recent L1 atoms, clusters them by keyword overlap,
        and creates one L2 scenario per cluster.

        Trigger: every ~5 sessions worth of atoms → one distillation run.
        """
        atoms = self.mem.get_tier_entries("l1", limit=max_atoms)
        if len(atoms) < 5:
            return {"success": True, "scenarios_created": 0, "atoms_processed": 0,
                    "message": "Need at least 5 atoms to create scenarios"}

        # Filter out already-clustered atoms
        fresh_atoms = [a for a in atoms if a.get("id", "") not in self._processed_l1_atoms]
        if not fresh_atoms:
            return {"success": True, "scenarios_created": 0, "atoms_processed": 0,
                    "message": "All atoms already clustered — nothing to distill"}

        clusters = _cluster_atoms(fresh_atoms, min_overlap=2)
        scenarios_created = 0

        for cluster in clusters:
            if len(cluster) < 2:
                continue  # skip singleton clusters

            # Determine cluster theme from most common fact_type
            type_counts: collections.Counter = collections.Counter()
            for a in cluster:
                ft = a.get("fact_type", "unknown")
                type_counts[ft] += 1
            dominant_types = [t for t, _ in type_counts.most_common(2)]

            # Build scenario block
            scenario_title = f"Cluster: {', '.join(dominant_types)} ({len(cluster)} atoms)"
            scenario_lines = [f"### {scenario_title}"]
            scenario_lines.append(f"*Generated: {_make_timestamp()}*")
            scenario_lines.append(f"*Source atoms: {len(cluster)}*")
            scenario_lines.append("")

            # Group atoms by type within the cluster
            by_type: dict[str, list[dict]] = {}
            for a in cluster:
                by_type.setdefault(a.get("fact_type", "unknown"), []).append(a)

            for ft, items in sorted(by_type.items()):
                scenario_lines.append(f"#### {ft.capitalize()} ({len(items)})")
                for item in items:
                    text = item.get("fact", item.get("text", ""))
                    conf = item.get("confidence", 0.5)
                    scenario_lines.append(f"- [{conf:.0%} conf] {text}")
                scenario_lines.append("")

            scenario_text = "\n".join(scenario_lines)
            self.mem.write_to_tier(
                tier="l2",
                entry=scenario_text,
                author="distillation-pipeline",
                metadata={
                    "cluster_size": len(cluster),
                    "dominant_types": dominant_types,
                    "atom_ids": [a.get("id", "") for a in cluster][:20],
                },
            )
            scenarios_created += 1

            # Mark atoms as processed
            for a in cluster:
                a_id = a.get("id", "")
                if a_id:
                    self._processed_l1_atoms.add(a_id)

        return {
            "success": True,
            "scenarios_created": scenarios_created,
            "atoms_processed": sum(len(c) for c in clusters),
            "clusters_found": len(clusters),
            "message": f"Created {scenarios_created} scenarios from {len(fresh_atoms)} atoms",
        }

    # ── L2 → L3: Synthesize persona from scenarios ─────────────────

    def distill_l2_to_l3(self) -> dict:
        """Synthesize L3 Persona from accumulated L2 Scenarios.

        Trigger: every ~50 L2 scenarios → one persona refresh.
        Aggregates all scenarios into a CEO-facing persona summary.
        """
        scenarios = self.mem.get_tier_entries("l2", limit=100)
        if len(scenarios) < 3:
            return {"success": True, "persona_updated": False, "scenarios_reviewed": len(scenarios),
                    "message": "Need at least 3 scenarios to synthesize persona"}

        # Extract all fact_types and their confidence-weighted counts
        fact_summary: dict[str, list[str]] = {}
        total_items = 0

        for s in scenarios:
            body = s.get("body", "")
            # Parse scenario items (lines starting with "- [X% conf] text")
            for line in body.split("\n"):
                m = re.match(r"- \[(\d+)% conf\]\s+(.+)", line.strip())
                if m:
                    confidence = int(m.group(1))
                    text = m.group(2).strip()
                    # Crude type inference from the section header context
                    ft = "general"
                    if "correction" in body[:200].lower():
                        ft = "correction"
                    elif "preference" in body[:200].lower():
                        ft = "preference"
                    elif "constraint" in body[:200].lower():
                        ft = "constraint"
                    elif "strategy" in body[:200].lower() or "decision" in body[:200].lower():
                        ft = "strategy"
                    fact_summary.setdefault(ft, []).append(
                        f"[{confidence}%] {text}"
                    )
                    total_items += 1

        if not fact_summary:
            return {"success": True, "persona_updated": False, "scenarios_reviewed": len(scenarios),
                    "message": "No extractable facts found in scenarios"}

        # Build persona document
        persona_lines = [
            f"# L3 Persona — Synthesized Profile",
            f"",
            f"> **Generated**: {_make_timestamp()}",
            f"> **Sources**: {len(scenarios)} L2 scenarios, {total_items} fact items",
            f"> **Method**: Automatic distillation pipeline (Phase B)",
            f"",
            f"## Profile Summary",
            f"",
        ]

        # Corrections & Constraints (highest signal)
        if "correction" in fact_summary or "constraint" in fact_summary:
            persona_lines.append("### 🔴 Corrections & Constraints (Highest Priority)")
            for ft in ("correction", "constraint"):
                if ft in fact_summary:
                    for item in fact_summary[ft][:10]:
                        persona_lines.append(f"- {item}")
            persona_lines.append("")

        # Preferences
        if "preference" in fact_summary:
            persona_lines.append("### 🟡 Preferences & Style")
            for item in fact_summary["preference"][:10]:
                persona_lines.append(f"- {item}")
            persona_lines.append("")

        # Strategy & Decisions
        if "strategy" in fact_summary:
            persona_lines.append("### 🟢 Strategy & Decisions")
            for item in fact_summary["strategy"][:10]:
                persona_lines.append(f"- {item}")
            persona_lines.append("")

        # General
        if "general" in fact_summary:
            persona_lines.append("### ⚪ General Facts")
            for item in fact_summary["general"][:5]:
                persona_lines.append(f"- {item}")
            persona_lines.append("")

        persona_lines.append("---")
        persona_lines.append("*Generated by DistillationPipeline — review and refine manually.*")

        persona_text = "\n".join(persona_lines)
        self.mem.write_to_tier(
            tier="l3",
            entry=persona_text,
            author="distillation-pipeline",
            metadata={
                "source_scenarios": len(scenarios),
                "total_facts": total_items,
                "fact_categories": list(fact_summary.keys()),
            },
        )

        return {
            "success": True,
            "persona_updated": True,
            "scenarios_reviewed": len(scenarios),
            "facts_aggregated": total_items,
            "categories": list(fact_summary.keys()),
            "message": f"Synthesized persona from {len(scenarios)} scenarios ({total_items} facts)",
        }

    # ── Full pipeline ──────────────────────────────────────────────

    def auto_distill(self) -> dict:
        """Run the full distillation pipeline: L0→L1→L2→L3.

        Safe to call repeatedly — tracks what's been processed.
        Returns a summary of all three stages.
        """
        results: dict[str, dict] = {}

        # Stage 1: L0 → L1
        results["l0_to_l1"] = self.distill_l0_to_l1()

        # Stage 2: L1 → L2 (if enough new atoms accumulated)
        results["l1_to_l2"] = self.distill_l1_to_l2()

        # Stage 3: L2 → L3 (periodic persona refresh)
        l2_count = len(self.mem.get_tier_entries("l2", limit=1000))
        if l2_count >= 3:
            results["l2_to_l3"] = self.distill_l2_to_l3()
        else:
            results["l2_to_l3"] = {
                "success": True, "persona_updated": False, "scenarios_reviewed": l2_count,
                "message": f"Insufficient L2 scenarios ({l2_count}) for persona synthesis",
            }

        # Summary
        total_facts = results["l0_to_l1"].get("facts_extracted", 0)
        total_scenarios = results["l1_to_l2"].get("scenarios_created", 0)
        persona_updated = results["l2_to_l3"].get("persona_updated", False)

        return {
            "success": True,
            "stages": {k: v.get("message", "") for k, v in results.items()},
            "summary": {
                "facts_extracted": total_facts,
                "scenarios_created": total_scenarios,
                "persona_updated": persona_updated,
            },
            "details": results,
        }

    def get_status(self) -> dict:
        """Inspect distillation readiness — what can be processed next."""
        self.mem._ensure_tier_dirs()

        l0_count = len(list(TIER_DIRS["l0"].glob("l0-*.md"))) if TIER_DIRS["l0"].exists() else 0
        l1_count = len(self.mem.get_tier_entries("l1", limit=10000))
        l2_count = len(self.mem.get_tier_entries("l2", limit=10000))
        l3_count = len(self.mem.get_tier_entries("l3", limit=10000))

        unprocessed_l0 = max(0, l0_count - len(self._processed_l0))

        return {
            "tiers": {
                "l0": {"files": l0_count, "unprocessed": unprocessed_l0},
                "l1": {"atoms": l1_count, "unclustered": max(0, l1_count - len(self._processed_l1_atoms))},
                "l2": {"scenarios": l2_count},
                "l3": {"personas": l3_count},
            },
            "ready_to_distill": {
                "l0_to_l1": unprocessed_l0 > 0,
                "l1_to_l2": l1_count >= 5 and (l1_count - len(self._processed_l1_atoms)) > 0,
                "l2_to_l3": l2_count >= 3,
            },
        }

# ---------------------------------------------------------------------------
# Seed the shared memory
# ---------------------------------------------------------------------------
def seed_shared_memory(memory_file: Optional[Path] = None) -> None:
    mem = SharedMemory(memory_file)
    if mem.memory_file.exists():
        return
    entries = [
        (
            "修正：晨报员（ops/morning-brief）在生成每日晨报时，"
            "必须包含当日主要股指数据（上证、深证、恒生、纳斯达克），"
            "而不仅是文字摘要。数据源使用 Yahoo Finance API。",
            "ops/morning-brief",
        ),
        (
            "修正：所有对外邮件必须使用统一签名模板：\n\n"
            "Best regards,\n[Name]\nMoxt.ai Team\n——\n"
            "邮件首行必须以 \"Hi [Name]\" 开头，禁止使用 \"Dear\"、\"Hello\"、\"Hey\" 等非规范问候语。",
            "human:CEO",
        ),
        (
            "已确认：目标客户画像关键词 = [\"SaaS\", \"AI agent\", \"developer tools\", "
            "\"LLM\", \"automation\"]。\n理想客户规模：10-200 人技术团队。\n"
            "决策者角色：CTO / VP Engineering / Head of AI。\n排除行业：政府、军工、金融。",
            "sales/cold-outreach",
        ),
    ]
    for entry, author in entries:
        mem.write_memory(entry, author=author)
    print(f"✓ Seeded {len(entries)} memory entries into {mem.memory_file}")


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
        print(f'No results found for: "{query}"')
        return
    print(f'Found {len(results)} result(s) for "{query}":\n')
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
        print(f'✓ Corrected {result["matched"]} entry(ies) matching: "{correction_id}"')
    else:
        print(f'✗ Error: {result.get("error", "unknown")}', file=sys.stderr)
        sys.exit(1)


def cmd_namespaces(mem: SharedMemory) -> None:
    """List namespaces and their entry counts."""
    namespaces = mem.list_namespaces()
    print("Available Memory Namespaces:\n")
    for ns in namespaces:
        entries = mem.get_namespace_entries(ns["id"])
        print(f"  [{ns['id']:12}] {ns['desc']}")
        print(f"              Access: {ns['access']} | Entries: {len(entries)} | "
              f"Retention: {ns['retention_days'] or 'forever'}d")


def cmd_gate_mem_export(mem: SharedMemory) -> None:
    """Export memory in GateMem-compatible format."""
    export = mem.gate_mem_compat_export()
    print(json.dumps(export, ensure_ascii=False, indent=2))


def cmd_distill(mem: SharedMemory, stage: Optional[str] = None) -> None:
    """Run the distillation pipeline (L0→L1→L2→L3)."""
    pipe = DistillationPipeline(mem)

    if stage == "status":
        status = pipe.get_status()
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return

    print("🧪 Running distillation pipeline...\n")
    result = pipe.auto_distill()

    summary = result["summary"]
    print(f"  Facts extracted:    {summary['facts_extracted']}")
    print(f"  Scenarios created:  {summary['scenarios_created']}")
    print(f"  Persona updated:    {'✅' if summary['persona_updated'] else '⏭️  (insufficient scenarios)'}")
    print()

    # Print stage details
    for stage_name, msg in result["stages"].items():
        print(f"  [{stage_name}] {msg}")

    if summary["facts_extracted"] == 0 and summary["scenarios_created"] == 0:
        print("\n💡 No new content to distill. Add L0 conversations first.")
        print("   echo '## [2026-05-15 10:00] user\\ntest content' >> memory/tiers/l0-conversations/l0-2026-05-15.md")


def cmd_compress(mem: SharedMemory, path: Optional[str] = None,
                 text: Optional[str] = None, stats_only: bool = False,
                 mermaid_only: bool = False) -> None:
    """Symbolic compression — L0 session → Mermaid graph."""
    if text:
        result = mem.compress_session(l0_text=text, session_id="inline")
    elif path:
        l0_path = Path(path)
        if not l0_path.exists():
            print(f"✗ File not found: {path}", file=sys.stderr)
            sys.exit(1)
        result = mem.compress_session(l0_path=l0_path)
    else:
        # Default: compress the most recent L0 file
        l0_dir = TIER_DIRS["l0"]
        if not l0_dir.exists():
            print("✗ L0 directory does not exist. Create L0 content first.", file=sys.stderr)
            sys.exit(1)
        l0_files = sorted(l0_dir.glob("l0-*.md"), reverse=True)
        if not l0_files:
            print("✗ No L0 session files found.", file=sys.stderr)
            sys.exit(1)
        result = mem.compress_session(l0_path=l0_files[0])

    if not result["success"]:
        print(f"✗ Compression failed: {result.get('error', 'unknown')}", file=sys.stderr)
        sys.exit(1)

    if stats_only:
        stats = result["token_stats"]
        print(f"Session: {result.get('node_count', 0)} tool calls")
        print(f"Raw:      {stats['raw_chars']:,} chars (~{stats['raw_tokens_est']:,} tokens)")
        print(f"Compressed: {stats['compressed_chars']:,} chars (~{stats['compressed_tokens_est']:,} tokens)")
        print(f"Saved:    {stats['savings_tokens_est']:,} tokens ({stats['compression_ratio']:.0%} savings)")
        return

    if mermaid_only:
        print(result["mermaid"])
        return

    print(result["summary_text"])
    print()
    print("── Mermaid Graph ──")
    print(result["mermaid"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hermes Team Shared Memory — correct once, all agents learn",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  hermes-memory.py show
  hermes-memory.py add "竞品监控应包含 GitHub trending"
  hermes-memory.py add --author "human:CEO" --ns personal "私人备忘"
  hermes-memory.py search "晨报"
  hermes-memory.py correct "ops/morning-brief" "新的修正内容"
  hermes-memory.py context
  hermes-memory.py namespaces
  hermes-memory.py gate-mem-export
  hermes-memory.py distill
  hermes-memory.py distill --status
""",
    )
    sub = parser.add_subparsers(dest="command", help="Command")

    sub.add_parser("show", help="Display full shared memory")

    p_add = sub.add_parser("add", help="Add a correction/learning entry")
    p_add.add_argument("entry", help="The memory entry text")
    p_add.add_argument("--author", "-a", default="human", help="Author identifier")
    p_add.add_argument("--ns", "--namespace", default="shared",
                       help="Namespace (shared/personal/board/audit)")

    p_search = sub.add_parser("search", help="Search memory by keyword")
    p_search.add_argument("query", help="Search keyword or phrase")

    p_correct = sub.add_parser("correct", help="Update a specific memory entry")
    p_correct.add_argument("correction_id", help="Identifier to match the entry")
    p_correct.add_argument("new_content", help="Replacement body content")

    sub.add_parser("context", help="Print compressed context for coworker injection")
    sub.add_parser("namespaces", help="List available memory namespaces")
    sub.add_parser("gate-mem-export", help="Export in GateMem-compatible JSON format")
    sub.add_parser("seed", help="Seed the shared memory with example entries")

    p_distill = sub.add_parser("distill", help="Run the memory distillation pipeline (L0→L1→L2→L3)")
    p_distill.add_argument("--status", action="store_true", help="Show distillation readiness")

    p_compress = sub.add_parser("compress", help="Symbolic compression — L0 session → Mermaid graph")
    p_compress.add_argument("path", nargs="?", help="Path to L0 session file")
    p_compress.add_argument("--text", "-t", help="Compress inline text instead of a file")
    p_compress.add_argument("--stats", action="store_true", help="Show compression stats only")
    p_compress.add_argument("--mermaid", action="store_true", help="Output Mermaid graph only")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    mem = SharedMemory()

    if args.command == "show":
        cmd_show(mem)
    elif args.command == "add":
        ns = getattr(args, 'ns', 'shared')
        author = args.author
        if ns != "shared":
            result = mem.write_to_namespace(args.entry, author=author, namespace=ns)
            if result["success"]:
                print(f"✓ Memory entry added to [{ns}]: {result['entry_id']}")
            else:
                print(f"✗ Error: {result.get('error')}", file=sys.stderr)
                sys.exit(1)
        else:
            cmd_add(mem, args.entry, author=args.author)
    elif args.command == "search":
        cmd_search(mem, args.query)
    elif args.command == "correct":
        cmd_correct(mem, args.correction_id, args.new_content)
    elif args.command == "context":
        cmd_context(mem)
    elif args.command == "namespaces":
        cmd_namespaces(mem)
    elif args.command == "gate-mem-export":
        cmd_gate_mem_export(mem)
    elif args.command == "seed":
        seed_shared_memory()
    elif args.command == "distill":
        cmd_distill(mem, stage="status" if args.status else None)
    elif args.command == "compress":
        cmd_compress(mem, path=args.path, text=args.text,
                     stats_only=args.stats, mermaid_only=args.mermaid)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
