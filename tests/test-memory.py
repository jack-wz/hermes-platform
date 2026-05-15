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


# ---------------------------------------------------------------------------
# Phase B — Distillation Pipeline Tests
# ---------------------------------------------------------------------------

class TestDistillationPipeline(unittest.TestCase):
    """Test the DistillationPipeline (L0 → L1 → L2 → L3)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mem_file = Path(self.tmp.name) / "SHARED_MEMORY.md"
        self.mem = SharedMemory(self.mem_file)
        # Override tier dirs to use temp
        import hermes_memory
        hermes_memory.TIER_DIRS = {
            "l0": Path(self.tmp.name) / "tiers" / "l0-conversations",
            "l1": Path(self.tmp.name) / "tiers" / "l1-atoms",
            "l2": Path(self.tmp.name) / "tiers" / "l2-scenarios",
            "l3": Path(self.tmp.name) / "tiers" / "l3-personas",
        }
        self.mem._ensure_tier_dirs()
        self.pipe = hermes_memory.DistillationPipeline(self.mem)

    def tearDown(self):
        # Restore original TIER_DIRS
        import hermes_memory
        hermes_memory.TIER_DIRS = {
            "l0": hermes_memory.MEMORY_TIERS_DIR / "l0-conversations",
            "l1": hermes_memory.MEMORY_TIERS_DIR / "l1-atoms",
            "l2": hermes_memory.MEMORY_TIERS_DIR / "l2-scenarios",
            "l3": hermes_memory.MEMORY_TIERS_DIR / "l3-personas",
        }
        self.tmp.cleanup()

    def test_get_status_empty_tiers(self):
        status = self.pipe.get_status()
        self.assertEqual(status["tiers"]["l0"]["files"], 0)
        self.assertEqual(status["tiers"]["l1"]["atoms"], 0)
        self.assertFalse(status["ready_to_distill"]["l0_to_l1"])

    def test_l0_to_l1_fact_extraction(self):
        """Write a sample L0 entry, then distill L0→L1."""
        # Seed L0 with conversations containing extractable facts
        self.mem.write_to_tier("l0", "修正：所有报告必须包含日期。\n偏好：压缩格式汇报。\n记住：项目路径 /Users/aiutb/hermes-platform", author="human:CEO")
        self.mem.write_to_tier("l0", "禁止使用外部API。\n策略：优先内存升级。\n已确认：目标用户是开发者。", author="board:execution")

        result = self.pipe.distill_l0_to_l1()
        self.assertTrue(result["success"])
        self.assertGreaterEqual(result["facts_extracted"], 3,
                                f"Expected >=3 facts, got {result['facts_extracted']}")

        # Verify L1 atoms were written
        l1 = self.mem.get_tier_entries("l1", limit=100)
        self.assertGreaterEqual(len(l1), 3, f"Expected >=3 L1 atoms, got {len(l1)}")

        # Check specific fact types
        fact_types = [a.get("fact_type") for a in l1]
        self.assertIn("correction", fact_types)
        self.assertIn("preference", fact_types)
        self.assertIn("constraint", fact_types)

    def test_l0_to_l1_idempotent(self):
        """Running distill_l0_to_l1 twice should not double-extract."""
        self.mem.write_to_tier("l0", "修正：测试内容。", author="test")
        r1 = self.pipe.distill_l0_to_l1()
        self.assertGreater(r1["facts_extracted"], 0, "First run should extract facts")
        r2 = self.pipe.distill_l0_to_l1()
        self.assertEqual(r2["facts_extracted"], 0,
                         "Idempotency: second run should extract 0 new facts")

    def test_l1_to_l2_clustering(self):
        """Pre-seed L1 with related atoms, verify clustering.

        Uses content with intentional keyword overlap between entries
        so the greedy clustering algorithm can group them into scenarios.
        """
        # Content engineered for CJK+ASCII keyword overlap:
        # - Group 1 (corrections): all about "代码测试" workflow
        # - Group 2 (preferences): all about "Python开发" style
        self.mem.write_to_tier("l0", (
            "修正：代码需要测试覆盖。\n修正：测试代码必须通过review。\n修正：代码review后才能合并。\n"
            "偏好：Python开发优先。\n偏好：Python代码风格用black。\n"
            "记住：数据库密码在.env文件。\n"
        ), author="dev:lead")
        self.pipe.distill_l0_to_l1()

        # Now distill L1 → L2
        r = self.pipe.distill_l1_to_l2()
        self.assertTrue(r["success"])
        self.assertGreaterEqual(r["scenarios_created"], 1,
                                f"Expected >=1 scenario, got {r['scenarios_created']}")

        # Verify L2 entries exist
        l2 = self.mem.get_tier_entries("l2", limit=10)
        self.assertGreaterEqual(len(l2), 1, f"Expected >=1 L2 scenario, got {len(l2)}")

    def test_l1_to_l2_insufficient_atoms(self):
        """Should not create scenarios with < 5 atoms."""
        self.mem.write_to_tier("l1", "single fact", author="test",
                               metadata={"fact_type": "correction", "confidence": 0.9})
        r = self.pipe.distill_l1_to_l2()
        self.assertTrue(r["success"])
        self.assertEqual(r["scenarios_created"], 0)

    def test_l2_to_l3_insufficient_scenarios(self):
        """Should not synthesize persona with < 3 scenarios."""
        r = self.pipe.distill_l2_to_l3()
        self.assertFalse(r["persona_updated"])
        self.assertEqual(r["scenarios_reviewed"], 0)

    def test_l2_to_l3_persona_synthesis(self):
        """Full pipeline: L0→L1→L2→L3."""
        # Seed enough L0 content for a full distillation
        self.mem.write_to_tier("l0", (
            "修正：日报必须包含数字。\n修正：邮件签名要统一。\n"
            "禁止：使用emoji在正式报告。\n"
            "偏好：中文汇报，技术细节用英文。\n"
            "策略：优先开发memory能力。\n"
            "已确认：目标客户是SaaS公司。\n"
            "记住：CEO偏好压缩汇报。\n"
        ), author="human:CEO")
        self.mem.write_to_tier("l0", (
            "修正：Git push先commit再push。\n修正：时间戳用UTC。\n"
            "偏好：测试先于实现。\n"
            "策略：纯Python实现优先。\n"
        ), author="team:build")

        # Run full pipeline
        pipe2 = hermes_memory.DistillationPipeline(self.mem)
        r = pipe2.auto_distill()

        self.assertTrue(r["success"])
        self.assertGreater(r["summary"]["facts_extracted"], 0)
        self.assertGreater(r["summary"]["scenarios_created"], 0)

    def test_auto_distill_status(self):
        """get_status should reflect distillation readiness."""
        self.mem.write_to_tier("l0", "修正：测试。", author="test")
        status = self.pipe.get_status()
        self.assertEqual(status["tiers"]["l0"]["files"], 1)
        self.assertEqual(status["tiers"]["l0"]["unprocessed"], 1)
        self.assertTrue(status["ready_to_distill"]["l0_to_l1"])

        # After distilling L0→L1, readiness should change
        self.pipe.distill_l0_to_l1()
        status2 = self.pipe.get_status()
        self.assertEqual(status2["tiers"]["l0"]["unprocessed"], 0)
        self.assertFalse(status2["ready_to_distill"]["l0_to_l1"])

    def test_fact_extraction_patterns(self):
        """Verify specific fact extraction patterns."""
        facts = hermes_memory._extract_facts_from_text(
            "修正：所有代码必须写测试。\n"
            "禁止使用eval()。\n"
            "偏好：简洁回复。\n"
            "已确认：周五发版。\n"
            "策略：先做memory再搞pipeline。\n"
            "记住：项目根目录是 ~/hermes-platform。\n"
            "https://github.com/jack-wz/hermes-platform 是主仓库。\n"
            "文件在 /Users/aiutb/hermes-platform/hermes-memory.py。\n"
        )
        types = [f["type"] for f in facts]
        self.assertIn("correction", types)
        self.assertIn("constraint", types)
        self.assertIn("preference", types)
        self.assertIn("decision", types)
        self.assertIn("strategy", types)
        self.assertIn("reminder", types)
        self.assertIn("url", types)
        self.assertIn("file_path", types)

    def test_keyword_overlap_similar(self):
        a = {"fact": "代码修正必须写测试"}
        b = {"fact": "所有代码需要测试覆盖"}
        overlap = hermes_memory._keyword_overlap(a, b)
        self.assertGreaterEqual(overlap, 2)

    def test_keyword_overlap_different(self):
        a = {"fact": "代码修正必须写测试"}
        b = {"fact": "中午吃饭在食堂二楼"}
        overlap = hermes_memory._keyword_overlap(a, b)
        self.assertEqual(overlap, 0)

    def test_cluster_atoms(self):
        atoms = [
            {"fact": "修正：代码要review", "fact_type": "correction"},
            {"fact": "修正：review后才能合并", "fact_type": "correction"},
            {"fact": "偏好：用Python开发", "fact_type": "preference"},
            {"fact": "偏好：Python优先", "fact_type": "preference"},
            {"fact": "食堂在二楼", "fact_type": "general"},
        ]
        clusters = hermes_memory._cluster_atoms(atoms, min_overlap=1)
        self.assertGreaterEqual(len(clusters), 2, f"Expected >=2 clusters, got {len(clusters)}")
        # The two corrections should be in the same cluster
        # The two preferences should be in the same cluster
        cluster_sizes = [len(c) for c in clusters]
        self.assertEqual(sum(cluster_sizes), 5, "All atoms should be in clusters")
