#!/usr/bin/env python3
"""
Unit tests for hermes-memory.py — Shared Memory Layer.

Tests the SharedMemory class API using the actual module interface.
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Load hermes-memory.py as a module (filename has hyphen, can't use regular import)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MEMORY_PATH = PROJECT_ROOT / "build" / "workspace" / "hermes-memory.py"
spec = importlib.util.spec_from_file_location("hermes_memory", MEMORY_PATH)
hermes_memory = importlib.util.module_from_spec(spec)
sys.modules["hermes_memory"] = hermes_memory
spec.loader.exec_module(hermes_memory)

SharedMemory = hermes_memory.SharedMemory  # type: ignore


class TestSharedMemoryAPI(unittest.TestCase):
    """Test the SharedMemory Python API."""

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
        """read_memory() returns raw text string."""
        content = self.mem.read_memory()
        self.assertIsInstance(content, str)
        self.assertIn("human:CEO", content)
        self.assertIn("GitHub trending", content)

    def test_get_all_entries(self):
        """get_all_entries() returns list of structured dicts."""
        entries = self.mem.get_all_entries()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["author"], "human:CEO")
        self.assertIn("body", entries[0])

    def test_write_memory(self):
        result = self.mem.write_memory(
            "新修正：签名格式改为 姓名+职位",
            author="human:CTO",
        )
        self.assertTrue(result["success"])
        self.assertIn("entry_id", result)
        entries = self.mem.get_all_entries()
        self.assertEqual(len(entries), 3)

    def test_correct_memory(self):
        """Test the Moxt.ai killer feature: correct once, all remember."""
        result = self.mem.correct_memory(
            "human:CEO",
            "修正（已更新）：所有外部沟通必须包含公司官网 + LinkedIn。",
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["matched"], 1)

        entries = self.mem.get_all_entries()
        ceo_entry = [e for e in entries if e["author"] == "human:CEO"]
        self.assertEqual(len(ceo_entry), 1)
        self.assertIn("LinkedIn", ceo_entry[0]["body"])

    def test_search_memory(self):
        results = self.mem.search_memory("GitHub")
        self.assertEqual(len(results), 1)
        self.assertIn("header", results[0])
        self.assertIn("body", results[0])

        results = self.mem.search_memory("nonexistent")
        self.assertEqual(len(results), 0)

    def test_get_team_context(self):
        ctx = self.mem.get_team_context(max_entries=5)
        self.assertIsInstance(ctx, str)
        self.assertIn("human:CEO", ctx)
        self.assertIn("Shared Memory", ctx)
        self.assertIn("HUMAN CORRECTIONS", ctx)

    def test_idempotent_seed(self):
        """seed_shared_memory() should not overwrite existing file."""
        from hermes_memory import seed_shared_memory  # type: ignore

        seed_shared_memory(memory_file=Path(self.tmp.name))
        entries = self.mem.get_all_entries()
        # Should still have original 2 entries, not 3 seeded ones
        self.assertEqual(len(entries), 2)


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
        self.assertTrue(self.tmp_path.exists())

        content = self.tmp_path.read_text(encoding="utf-8")
        self.assertIn("第一条共享记忆", content)
        self.assertIn("test", content)

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
