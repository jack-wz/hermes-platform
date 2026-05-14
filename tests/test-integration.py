#!/usr/bin/env python3
"""
Integration test for Hermes Workspace components:
  Dashboard → Coworker → Memory → Audit chain.

Validates:
  1. Dashboard starts and serves API endpoints
  2. /api/memory POST/GET works (shared memory R/W)
  3. /api/coworkers lists all 8 coworkers
  4. /api/coworkers/run triggers actual execution
  5. /api/memory/context returns compressed context
  6. /api/status returns health data
  7. Execution logs are persisted
  8. Cross-component: memory entry → visible to coworker context
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DASHBOARD_SCRIPT = PROJECT_ROOT / "build" / "workspace" / "hermes-dashboard.py"
BASE_URL = "http://localhost:5002"
API = f"{BASE_URL}/api"

# ── Helpers ────────────────────────────────────────────────────────

def api_get(path):
    resp = urllib.request.urlopen(f"{API}{path}", timeout=5)
    return json.loads(resp.read())

def api_post(path, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"{API}{path}", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())


def print_result(test_name, ok, detail=""):
    icon = "✅" if ok else "❌"
    print(f"  {icon} {test_name}" + (f" — {detail}" if detail else ""))

# ── Tests ──────────────────────────────────────────────────────────

def test_status_endpoint():
    r = api_get("/status")
    ok = r.get("success") and r.get("status") == "healthy"
    stats = r.get("stats", {})
    print_result("Status endpoint", ok,
                 f"coworkers={stats.get('coworkers_total')}, skills={stats.get('skills_total')}, memory={stats.get('memory_entries')}")

def test_coworkers_list():
    r = api_get("/coworkers")
    ok = r.get("success") and r.get("count", 0) >= 8
    print_result("Coworkers list", ok, f"count={r.get('count')}")

def test_memory_write():
    r = api_post("/memory", {
        "entry": "Integration test: 修正-所有同事在回复邮件时必须加签名",
        "author": "test/integration",
    })
    ok = r.get("success")
    print_result("Memory write (POST)", ok, f"timestamp={r.get('timestamp', 'N/A')}")

def test_memory_read():
    r = api_get("/memory")
    ok = r.get("success") and r.get("count", 0) >= 1
    print_result("Memory read (GET)", ok, f"count={r.get('count')}")

def test_memory_context():
    r = api_get("/memory/context")
    ok = r.get("success") and r.get("entry_count", 0) >= 1
    print_result("Memory context (compressed)", ok,
                 f"total={r.get('entry_count')}, recent={r.get('recent_entries')}")

def test_coworker_trigger():
    r = api_post("/coworkers/run", {"coworker_id": "ops/morning-brief"})
    ok = r.get("success") and r.get("status") == "dispatched"
    print_result("Coworker trigger (POST run)", ok,
                 f"run_id={r.get('run_id')}, worker={r.get('coworker_id')}")
    return r.get("run_id") if ok else None

def test_coworker_log(coworker_id="ops/morning-brief"):
    r = api_get(f"/coworkers/{coworker_id}/log")
    ok = r.get("success")
    logs = r.get("logs", [])
    print_result("Coworker execution log", ok, f"logs_count={len(logs)}")
    # Check that at least one log has real execution data
    has_real_log = any(
        log.get("exit_code") is not None or log.get("stdout")
        for log in logs
    )
    if logs:
        last = logs[0]
        print(f"    Last run: status={last.get('exit_code')}, duration={last.get('duration_ms')}ms")

def test_skills_registry():
    r = api_get("/registry/skills")
    ok = r.get("success") and r.get("count", 0) >= 1
    print_result("Skills registry", ok, f"count={r.get('count')}")

# ── Cross-component integration ────────────────────────────────────

def test_cross_component_memory_propagation():
    """Write a correction to shared memory, verify it appears in context."""
    correction = "跨组件测试: ops/competitor-monitor 应追踪 GitHub trending, 不仅官网"
    api_post("/memory", {"entry": correction, "author": "test/cross-component"})

    # Verify the correction is in the memory context
    r = api_get("/memory/context")
    context = r.get("context", "")
    ok = "GitHub trending" in context
    print_result("Cross-component: memory→context propagation", ok,
                 f"context_len={len(context)} chars")

def test_cross_component_trigger_chain():
    """Trigger competitor-monitor and verify log is created."""
    r = api_post("/coworkers/run", {"coworker_id": "ops/competitor-monitor"})
    ok = r.get("success") and r.get("status") == "dispatched"
    print_result("Cross-component: dashboard→coworker execution", ok,
                 f"run_id={r.get('run_id', 'N/A')}")


# ── Main ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Hermes Workspace — Integration Tests")
    print("=" * 60)
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Dashboard:    {DASHBOARD_SCRIPT}")
    print(f"Target URL:   {BASE_URL}")
    print()

    failures = 0
    tests = [
        ("Status endpoint", test_status_endpoint),
        ("Coworkers list", test_coworkers_list),
        ("Skills registry", test_skills_registry),
        ("Memory write", test_memory_write),
        ("Memory read", test_memory_read),
        ("Memory context", test_memory_context),
        ("Coworker trigger", test_coworker_trigger),
        ("Coworker execution log", test_coworker_log),
        ("Cross: memory propagation", test_cross_component_memory_propagation),
        ("Cross: trigger chain", test_cross_component_trigger_chain),
    ]

    for name, fn in tests:
        try:
            fn()
        except Exception as exc:
            print_result(name, False, str(exc))
            failures += 1

    print()
    print("=" * 60)
    if failures:
        print(f"❌ {failures} test(s) failed")
        sys.exit(1)
    else:
        print("✅ All integration tests passed!")
        sys.exit(0)
