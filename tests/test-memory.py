#!/usr/bin/env python3
"""
Unit tests for hermes-memory.py v1.2 — Shared Memory Layer with Namespace Support.

Tests the SharedMemory class API including v1.2 namespace features.
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MEMORY_PATH = PROJECT_ROOT / "build" / "workspace" / "hermes-memory.py"
spec = importlib.util.spec_from_file_location("hermes_memory", MEMORY_PATH)
hermes_memory = importlib.util.module_from_spec(spec)
sys.modules["hermes_memory"] = hermes_memory
spec.loader.exec_module(hermes_memory)

SharedMemory = hermes_memory.SharedMemory
seed_shared_memory = hermes_memory.seed_shared_memory


class TestSharedMemoryAPI(unittest.TestCase):
    """Test the SharedMemory Python API (v1.0/v1.1 compatibility)."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w")
        self.tmp.write(
            "# Team Shared Memory\n\n"
            "> 纠正一个 Agent 犯的错，团队里所有 Agent 都记住了。\n\n"
            "## [2026-05-14 10:00] human:CEO\n"
            "修正：所有外部沟通必须包含公司官网链接。\n\n"
            "## [2026-05-14 10:30] ops/morning-brief\n"
            "竞品监控添加 GitHub trending 数据源。\n\n"
        )
        self.tmp.close()
        self.mem = SharedMemory(Path(self.tmp.name))

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_read_memory_raw(self):
        content = self.mem.read_memory()
        self.assertIsInstance(content, str)
        self.assertIn("human:CEO", content)

    def test_get_all_entries(self):
        entries = self.mem.get_all_entries()
        self.assertEqual(len(entries), 2)

    def test_write_memory(self):
        result = self.mem.write_memory("新修正", author="human:CTO")
        self.assertTrue(result["success"])
        self.assertEqual(len(self.mem.get_all_entries()), 3)

    def test_correct_memory(self):
        result = self.mem.correct_memory(
            "human:CEO", "修正（已更新）：含 LinkedIn。"
        )
        self.assertTrue(result["success"])
        entries = self.mem.get_all_entries()
        ceo = [e for e in entries if e["author"] == "human:CEO"]
        self.assertIn("LinkedIn", ceo[0]["body"])

    def test_search_memory(self):
        results = self.mem.search_memory("GitHub")
        self.assertEqual(len(results), 1)

        results = self.mem.search_memory("nonexistent")
        self.assertEqual(len(results), 0)

    def test_get_team_context(self):
        ctx = self.mem.get_team_context(max_entries=5)
        self.assertIn("human:CEO", ctx)
        self.assertIn("HUMAN CORRECTIONS", ctx)

    def test_idempotent_seed(self):
        seed_shared_memory(memory_file=Path(self.tmp.name))
        entries = self.mem.get_all_entries()
        self.assertEqual(len(entries), 2)


class TestNamespaceAPI(unittest.TestCase):
    """Test v1.2 namespace features."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mem_file = Path(self.tmp.name) / "SHARED_MEMORY.md"
        # Override namespaces dir to use temp
        self.mem = SharedMemory(self.mem_file)
        self.mem._namespace_dir = Path(self.tmp.name) / "namespaces"
        self.mem._namespace_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_namespaces(self):
        namespaces = self.mem.list_namespaces()
        self.assertGreaterEqual(len(namespaces), 4)  # shared, personal, board, audit
        self.assertIn("shared", [ns["id"] for ns in namespaces])

    def test_write_to_namespace_personal(self):
        result = self.mem.write_to_namespace(
            "私人备忘：周五前完成审计报告",
            author="human:CEO",
            namespace="personal",
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["namespace"], "personal")
        self.assertIn("entry_id", result)
        self.assertIn("audit_hash", result)

    def test_write_to_invalid_namespace(self):
        result = self.mem.write_to_namespace(
            "测试", author="test", namespace="invalid_ns"
        )
        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_get_namespace_entries(self):
        self.mem.write_to_namespace("Entry 1", author="human", namespace="personal")
        self.mem.write_to_namespace("Entry 2", author="human", namespace="personal")
        entries = self.mem.get_namespace_entries("personal")
        self.assertGreaterEqual(len(entries), 2)

    def test_namespace_isolation(self):
        """Personal namespace entries should not appear in board namespace."""
        self.mem.write_to_namespace("Personal note", author="human", namespace="personal")
        board_entries = self.mem.get_namespace_entries("board")
        # Board namespace should be empty (hasn't been written to)
        self.assertEqual(len(board_entries), 0)

    def test_gate_mem_compat_export(self):
        self.mem.write_to_namespace("Shared entry", author="test", namespace="shared")
        self.mem.write_to_namespace("Personal entry", author="human", namespace="personal")
        export = self.mem.gate_mem_compat_export()
        self.assertEqual(export["format"], "gate-mem-v1")
        self.assertIn("principals", export)
        self.assertIn("shared", export["principals"])
        self.assertIn("personal", export["principals"])

    def test_audit_hash_consistency(self):
        """Same content + author + timestamp should produce same audit_hash."""
        r1 = self.mem.write_to_namespace("Test content", author="test", namespace="audit")
        r2 = self.mem.write_to_namespace("Test content", author="test", namespace="audit")
        # Same content within same second → same hash (deterministic)
        self.assertEqual(r1["audit_hash"], r2["audit_hash"])
        
        # Different content → different hash
        r3 = self.mem.write_to_namespace("Different content", author="test", namespace="audit")
        self.assertNotEqual(r1["audit_hash"], r3["audit_hash"])


class TestMemoryWriteFile(unittest.TestCase):
    """Test writing to a fresh memory file."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".md", delete=False)
        self.tmp_path = Path(self.tmp.name)
        self.tmp.close()

    def tearDown(self):
        if self.tmp_path.exists():
            os.unlink(self.tmp_path)

    def test_write_to_new_file(self):
        mem = SharedMemory(self.tmp_path)
        result = mem.write_memory("第一条共享记忆", author="test")
        self.assertTrue(result["success"])
        content = self.tmp_path.read_text(encoding="utf-8")
        self.assertIn("第一条共享记忆", content)

    def test_list_entries_empty_file(self):
        mem = SharedMemory(self.tmp_path)
        entries = mem.get_all_entries()
        self.assertEqual(len(entries), 0)

    def test_context_empty_file(self):
        mem = SharedMemory(self.tmp_path)
        ctx = mem.get_team_context()
        self.assertIn("contains no entries", ctx)


if __name__ == "__main__":
    unittest.main(verbosity=2)
