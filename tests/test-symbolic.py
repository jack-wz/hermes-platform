#!/usr/bin/env python3
"""
Unit tests for symbolic_memory.py — Phase C: Symbolic Memory Compression.
"""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SYMBOLIC_PATH = PROJECT_ROOT / "build" / "workspace" / "symbolic_memory.py"

spec = importlib.util.spec_from_file_location("symbolic_memory", SYMBOLIC_PATH)
sm_module = importlib.util.module_from_spec(spec)
sys.modules["symbolic_memory"] = sm_module
spec.loader.exec_module(sm_module)

SymbolicMemory = sm_module.SymbolicMemory
SymbolGraph = sm_module.SymbolGraph
SymbolNode = sm_module.SymbolNode
_extract_tool_calls = sm_module._extract_tool_calls
_detect_status = sm_module._detect_status
_truncate = sm_module._truncate


# ── Sample session with tool calls ───────────────────────────────

SAMPLE_SESSION = """## [2026-05-15 10:00] agent:main
Ran web_search('hermes memory architecture') and found 5 results.
Decided to read the architecture document.

## [2026-05-15 10:01] agent:main
Used read_file('docs/architecture/memory-v2.md') for reference.
The file contains 123 lines of detailed architecture specs.

## [2026-05-15 10:02] agent:main
Ran terminal('cd hermes-platform && git push origin main')
exit_code=0 — pushed 3 commits.

## [2026-05-15 10:03] agent:main
Ran pytest tests/test-memory.py — all 29 tests PASSED in 0.04s.
Great results!

## [2026-05-15 10:04] agent:main
Ran terminal('pip install broken-package-999')
Traceback: ModuleNotFoundError — package not found.
"""

SESSION_WITH_ERRORS = """## [2026-05-15 10:00] agent:main
Ran terminal('git push origin main')
error: Permission denied (publickey).
fatal: Could not read from remote repository.
"""

SESSION_NO_TOOLS = """## [2026-05-15 10:00] human:CEO
请继续推进 Phase B 蒸馏管道开发。

## [2026-05-15 10:01] agent:main
好的，Phase B 已经开始。正在实现 L0→L1 提取器。
"""

LONG_OUTPUT = "line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\n" + \
              "\n".join(f"data line {i}" for i in range(50))


class TestToolExtraction(unittest.TestCase):
    """Test _extract_tool_calls and related helpers."""

    def test_extract_web_search(self):
        calls = _extract_tool_calls('web_search("hermes memory tool")')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["tool"], "web_search")
        self.assertEqual(calls[0]["arg"], "hermes memory tool")

    def test_extract_terminal(self):
        calls = _extract_tool_calls("terminal('git push origin main')")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["tool"], "terminal")

    def test_extract_multiple_tools(self):
        text = """web_search('query A')
terminal('cmd B')
read_file('path/to/file.md')
pytest tests/"""
        calls = _extract_tool_calls(text)
        self.assertGreaterEqual(len(calls), 4)

    def test_extract_git_push(self):
        calls = _extract_tool_calls("git push origin main")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["tool"], "git_push")

    def test_extract_empty(self):
        calls = _extract_tool_calls("hello world, no tools here")
        self.assertEqual(len(calls), 0)

    def test_detect_success(self):
        self.assertEqual(_detect_status("PASSED all tests"), "success")
        self.assertEqual(_detect_status("exit_code=0"), "success")
        self.assertEqual(_detect_status("✓ done"), "success")

    def test_detect_error(self):
        self.assertEqual(_detect_status("FAILED test"), "error")
        self.assertEqual(_detect_status("Traceback (most recent call last)"), "error")
        self.assertEqual(_detect_status("ModuleNotFoundError"), "error")
        self.assertEqual(_detect_status("Permission denied"), "error")

    def test_detect_neutral(self):
        self.assertEqual(_detect_status("hello world"), "neutral")

    def test_truncate_short(self):
        result = _truncate("short", max_lines=3, max_chars=100)
        self.assertEqual(result, "short")

    def test_truncate_long_lines(self):
        result = _truncate("line1\nline2\nline3\nline4\nline5", max_lines=3)
        self.assertIn("line1", result)
        self.assertIn("line2", result)
        self.assertIn("line3", result)
        self.assertIn("+2 lines", result)
        self.assertNotIn("line4", result)

    def test_truncate_long_chars(self):
        long_text = "x" * 300
        result = _truncate(long_text, max_chars=200)
        self.assertLess(len(result), 210)
        self.assertIn("...", result)


class TestSymbolicMemory(unittest.TestCase):
    """Test the SymbolicMemory compression engine."""

    def setUp(self):
        self.sm = SymbolicMemory()

    # ── Parse ────────────────────────────────────────────────────

    def test_parse_session_with_tools(self):
        nodes = self.sm.parse_session(SAMPLE_SESSION)
        self.assertGreaterEqual(len(nodes), 5,
                                f"Expected >=5 nodes, got {len(nodes)}")

        # Check tool types
        tools = [n.tool for n in nodes]
        self.assertIn("web_search", tools)
        self.assertIn("read_file", tools)
        self.assertIn("terminal", tools)
        self.assertIn("test_run", tools)

    def test_parse_session_no_tools(self):
        nodes = self.sm.parse_session(SESSION_NO_TOOLS)
        self.assertEqual(len(nodes), 0)

    def test_parse_session_with_errors(self):
        nodes = self.sm.parse_session(SESSION_WITH_ERRORS)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].status, "error")

    # ── Compress ─────────────────────────────────────────────────

    def test_compress_session_text(self):
        graph = self.sm.compress_session(session_text=SAMPLE_SESSION, session_id="test")
        self.assertIsInstance(graph, SymbolGraph)
        self.assertGreater(len(graph.nodes), 0)
        self.assertGreater(graph.raw_total_chars, 0)
        self.assertGreater(graph.compressed_chars, 0)

    def test_compress_empty_session(self):
        graph = self.sm.compress_session(session_text="no tools here at all",
                                          session_id="empty")
        self.assertEqual(len(graph.nodes), 0)
        self.assertEqual(graph.session_id, "empty")

    def test_compression_ratio(self):
        graph = self.sm.compress_session(session_text=SAMPLE_SESSION, session_id="test")
        ratio = graph.compression_ratio()
        self.assertGreaterEqual(ratio, 0.0)
        self.assertLessEqual(ratio, 1.0)

    def test_token_stats(self):
        graph = self.sm.compress_session(session_text=SAMPLE_SESSION, session_id="test")
        stats = graph.token_stats()
        self.assertIn("raw_chars", stats)
        self.assertIn("compressed_chars", stats)
        self.assertIn("savings_tokens_est", stats)
        self.assertIn("compression_ratio", stats)

    # ── Mermaid output ───────────────────────────────────────────

    def test_to_mermaid(self):
        graph = self.sm.compress_session(session_text=SAMPLE_SESSION, session_id="test")
        mermaid = graph.to_mermaid()
        self.assertIn("flowchart", mermaid)
        self.assertIn("-->", mermaid)  # edges

    def test_to_mermaid_no_tools(self):
        graph = self.sm.compress_session(session_text=SESSION_NO_TOOLS, session_id="test")
        mermaid = graph.to_mermaid()
        self.assertIn("flowchart", mermaid)
        self.assertIn("empty", mermaid.lower())

    def test_to_summary_text(self):
        graph = self.sm.compress_session(session_text=SAMPLE_SESSION, session_id="test")
        summary = graph.to_summary_text()
        self.assertIn("Symbolic Memory", summary)
        self.assertIn("Compression:", summary)

    # ── Drill-down ───────────────────────────────────────────────

    def test_drill_down(self):
        graph = self.sm.compress_session(session_text=SAMPLE_SESSION, session_id="test")
        if graph.nodes:
            node_id = graph.nodes[0].node_id
            raw = self.sm.drill_down(node_id)
            self.assertIsNotNone(raw, f"drill_down({node_id}) should return raw log")
            self.assertIn("web_search", raw)

    def test_drill_down_nonexistent(self):
        result = self.sm.drill_down("nonexistent-node-id")
        self.assertIsNone(result)

    def test_get_node_ids(self):
        self.sm.compress_session(session_text=SAMPLE_SESSION, session_id="test")
        ids = self.sm.get_node_ids()
        self.assertGreater(len(ids), 0)

    # ── File-based compression ───────────────────────────────────

    def test_compress_from_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(SAMPLE_SESSION)
            f.flush()
            graph = self.sm.compress_session(session_path=Path(f.name))
        self.assertGreater(len(graph.nodes), 0)
        Path(f.name).unlink()

    def test_compression_stats(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(SAMPLE_SESSION)
            f.flush()
            stats = self.sm.compression_stats(Path(f.name))
        self.assertIn("session_id", stats)
        self.assertIn("node_count", stats)
        self.assertIn("compression_ratio", stats)
        Path(f.name).unlink()

    # ── Long output compression ──────────────────────────────────

    def test_compress_long_output(self):
        """Very long tool output should compress significantly."""
        long_session = f"""## [2026-05-15 10:00] agent:main
terminal('find / -name "*.py"')
{LONG_OUTPUT}
"""
        graph = self.sm.compress_session(session_text=long_session, session_id="long")
        ratio = graph.compression_ratio()
        # With 58 lines of output + 1 tool call, compression should be significant
        self.assertGreater(ratio, 0.5,
                           f"Expected >50% savings on long output, got {ratio:.0%}")


class TestSymbolGraph(unittest.TestCase):
    """Test the SymbolGraph data class."""

    def test_empty_graph(self):
        graph = SymbolGraph(session_id="empty", nodes=[], raw_total_chars=0, compressed_chars=0)
        self.assertEqual(graph.session_id, "empty")
        self.assertEqual(graph.compression_ratio(), 0.0)
        self.assertIn("empty", graph.to_mermaid().lower())

    def test_single_node_graph(self):
        node = SymbolNode(
            node_id="n1", tool="web_search", icon="🔍",
            label="test query", summary="test query", status="success",
        )
        graph = SymbolGraph(session_id="test", nodes=[node],
                            raw_total_chars=500, compressed_chars=50)
        mermaid = graph.to_mermaid()
        self.assertIn("n1", mermaid)
        self.assertIn("web_search", mermaid)
        self.assertIn("✅", mermaid)

    def test_error_node(self):
        node = SymbolNode(
            node_id="n1", tool="terminal", icon="💻",
            label="rm -rf /", status="error",
        )
        graph = SymbolGraph(session_id="test", nodes=[node],
                            raw_total_chars=100, compressed_chars=20)
        mermaid = graph.to_mermaid()
        self.assertIn("❌", mermaid)

    def test_children_edges(self):
        n1 = SymbolNode(node_id="n1", tool="a", icon="🔍", label="",
                        children=["n2", "n3"], status="success")
        n2 = SymbolNode(node_id="n2", tool="b", icon="💻", label="", status="success")
        n3 = SymbolNode(node_id="n3", tool="c", icon="📄", label="", status="success")
        graph = SymbolGraph(session_id="test", nodes=[n1, n2, n3],
                            raw_total_chars=300, compressed_chars=60)
        mermaid = graph.to_mermaid()
        self.assertIn("n1 --> n2", mermaid)
        self.assertIn("n1 --> n3", mermaid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
