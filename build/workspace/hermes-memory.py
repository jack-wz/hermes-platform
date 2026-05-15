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
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
