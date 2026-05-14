#!/usr/bin/env python3
"""
Phase 4 End-to-End Test: Plugin Bridge with simulated execution flows.

Tests:
  1. Basic import and instantiation
  2. Handler registration (all 3 hooks)
  3. pre_execution: approve flow
  4. pre_execution: reject flow (short-circuit)
  5. pre_execution: parameter modification flow
  6. post_execution: augmentation flow
  7. error hook: transient error → retry
  8. error hook: fatal error → abort
  9. Full simulated execution: pre → run → post → audit
  10. Simulated error flow: pre → error hook
  11. Config file loading
  12. Built-in handlers via create_default_bridge()
  13. Handler introspection (registered_handlers)
  14. Handler chain ordering
  15. Multiple handlers per hook point

Run from the phase4 directory or with PYTHONPATH set correctly:
    cd ~/.hermes/workspace/build/phase4
    python3 test-bridge-e2e.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Ensure the phase4 directory is on sys.path so we can import the bridge
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hermes_plugin_bridge import (
    PluginBridge,
    PreExecutionDecision,
    PostExecutionResult,
    ErrorAction,
    create_default_bridge,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

PASS = 0
FAIL = 0

def check(test_name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {test_name}")
    else:
        FAIL += 1
        print(f"  ❌ {test_name}  — {detail}")

def section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

def subsection(title: str):
    print(f"\n  --- {title} ---")

# ---------------------------------------------------------------------------
# Sample skill metadata and input params (mirrors example-skill)
# ---------------------------------------------------------------------------

SKILL_META = {
    "skill_id": "devops/backup/git-auto-backup",
    "version": "1.0.0",
    "author": {"name": "team_build", "display": "技术开发·工匠长"},
    "description": "自动备份指定目录到远程 Git 仓库",
    "permissions": {
        "filesystem": {
            "read": ["~/.hermes/workspace/**"],
            "write": ["~/.hermes/backups/repos/"],
        },
        "network": {
            "domains": ["github.com", "api.github.com"],
            "ports": [443],
            "protocols": ["https"],
        },
        "tools": ["terminal", "file"],
        "credentials": [
            {"name": "GITHUB_TOKEN", "type": "env", "scope": "repo", "required": True}
        ],
    },
    "cost": {
        "token_estimate": {
            "base": 600,
            "per_run": {"input": 2500, "output": 1500, "total": 4000},
        },
        "api_cost_risk": "LOW",
    },
    "input": {
        "required": [
            {"name": "target_directory", "type": "string", "description": "备份目标目录"},
            {"name": "remote_url", "type": "string", "description": "远程仓库地址"},
        ],
        "optional": [
            {"name": "branch", "type": "string", "description": "目标分支", "default": "main"},
        ],
    },
    "output": {
        "success": {"schema": {"backup_id": "string", "commit_hash": "string"}},
        "failure": {"schema": {"error_code": "string", "error_message": "string"}},
    },
}

INPUT_PARAMS = {
    "target_directory": "/tmp/test-backup",
    "remote_url": "https://github.com/myorg/hermes-backup.git",
    "branch": "main",
}

# Sample execution result (post-execution)
EXEC_RESULT_SUCCESS = {
    "status": "success",
    "exit_code": 0,
    "stdout": '{"backup_id": "backup-20260514-120000", "commit_hash": "a1b2c3d"}',
    "stderr": "",
    "duration_ms": 1234,
    "started_at": "2026-05-14T12:00:00Z",
    "completed_at": "2026-05-14T12:00:01Z",
}

EXEC_RESULT_FAILURE = {
    "status": "failure",
    "exit_code": 1,
    "stdout": "",
    "stderr": "error_code=CONFLICT error_message='远程冲突' recoverable=false",
    "duration_ms": 567,
}

# Sample audit receipt
AUDIT_RECEIPT = {
    "receipt_id": "test-receipt-001",
    "timestamp": "2026-05-14T12:00:01Z",
    "skill": {"skill_id": "devops/backup/git-auto-backup", "rating": "B", "score": 82},
    "execution": {"status": "success", "duration_ms": 1234},
    "audit": {"token_cost": {"estimated_total_tokens": 4000, "estimated_cost_usd": 0.008}},
    "signature": "abc123",
}

ERROR_INFO_TRANSIENT = {
    "error_type": "TimeoutError",
    "error_message": "Connection to api.github.com timed out after 30s",
    "traceback": "Traceback (most recent call last):\n  ...",
    "skill_id": "devops/backup/git-auto-backup",
    "input_params": dict(INPUT_PARAMS),
}

ERROR_INFO_FATAL = {
    "error_type": "PermissionError",
    "error_message": "Permission denied: /etc/shadow",
    "traceback": "Traceback (most recent call last):\n  ...",
    "skill_id": "devops/backup/git-auto-backup",
    "input_params": dict(INPUT_PARAMS),
}

# ---------------------------------------------------------------------------
# Custom handler functions for testing
# ---------------------------------------------------------------------------

# Track call order for ordering tests
_call_log: list[str] = []

def _reset_call_log():
    _call_log.clear()


# --- Pre-execution handlers ---

def pre_approve_all(skill_meta, input_params):
    _call_log.append("pre_approve_all")
    return {"allow": True, "reason": "always ok"}


def pre_inject_trace(skill_meta, input_params):
    _call_log.append("pre_inject_trace")
    return {
        "allow": True,
        "reason": "injected trace_id",
        "modified_params": {"_trace_id": "trace-001", "_timestamp": "2026-05-14T12:00:00Z"},
    }


def pre_reject_dangerous(skill_meta, input_params):
    _call_log.append("pre_reject_dangerous")
    target = input_params.get("target_directory", "")
    if "/etc" in str(target):
        return {"allow": False, "reason": "拒绝访问系统目录 /etc"}
    return {"allow": True, "reason": "ok"}


def pre_scope_check(skill_meta, input_params):
    _call_log.append("pre_scope_check")
    perms = skill_meta.get("permissions", {})
    tools = perms.get("tools", [])
    if not tools:
        return {"allow": False, "reason": "技能未声明 tools — 拒绝执行"}
    return {"allow": True, "reason": f"tools declared: {tools}"}


# --- Post-execution handlers ---

def post_log_result(skill_meta, result, receipt):
    _call_log.append("post_log_result")
    return {"augmented": {"logged": True, "logger": "post_log_result"}}


def post_add_metadata(skill_meta, result, receipt):
    _call_log.append("post_add_metadata")
    return {"augmented": {"processed_by": "test-suite", "version": "1.0"}}


def post_failing_handler(skill_meta, result, receipt):
    """This handler deliberately raises — bridge should catch and continue."""
    _call_log.append("post_failing_handler")
    raise RuntimeError("simulated post_execution handler crash")


def post_after_failing(skill_meta, result, receipt):
    """Should still run even though the previous handler crashed."""
    _call_log.append("post_after_failing")
    return {"augmented": {"survived_crash": True}}


# --- Error handlers ---

def error_detect_transient(skill_meta, error_info):
    _call_log.append("error_detect_transient")
    msg = error_info.get("error_message", "").lower()
    if "timeout" in msg or "connection" in msg:
        return {"action": "retry", "reason": "Detected transient timeout error"}
    return {"action": "abort", "reason": "Not transient"}


def error_always_ignore(skill_meta, error_info):
    _call_log.append("error_always_ignore")
    return {"action": "ignore", "reason": "Test: always ignore"}


def error_escalate(skill_meta, error_info):
    _call_log.append("error_escalate")
    return {"action": "abort", "reason": "escalated to on-call"}


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def test_01_import_and_instantiate():
    section("Test 01: Import and instantiate PluginBridge")
    bridge = PluginBridge()
    check("PluginBridge imported", True)
    check("Instance created", isinstance(bridge, PluginBridge))
    check("No handlers registered initially",
          bridge.registered_handlers == {"pre_execution": [], "post_execution": [], "error": []})
    return bridge


def test_02_register_handlers(bridge):
    section("Test 02: Register handlers on all 3 hooks")
    bridge.clear()
    _reset_call_log()

    bridge.register_pre_execution(pre_approve_all, name="test.pre_approve_all")
    bridge.register_pre_execution(pre_inject_trace, name="test.pre_inject_trace")
    bridge.register_post_execution(post_log_result, name="test.post_log_result")
    bridge.register_error(error_detect_transient, name="test.error_detect_transient")

    h = bridge.registered_handlers
    check("2 pre_execution handlers",
          len(h["pre_execution"]) == 2)
    check("1 post_execution handler",
          len(h["post_execution"]) == 1)
    check("1 error handler",
          len(h["error"]) == 1)
    check("pre_execution names correct",
          h["pre_execution"] == ["test.pre_approve_all", "test.pre_inject_trace"])


def test_03_pre_execution_approve(bridge):
    section("Test 03: pre_execution — approve flow")
    bridge.clear()
    _reset_call_log()
    bridge.register_pre_execution(pre_approve_all, name="h1")

    decision = bridge.pre_execution(SKILL_META, INPUT_PARAMS)
    check("allow=True", decision.allow is True)
    check("reason populated", decision.reason == "always ok")
    check("handler was called", "pre_approve_all" in _call_log)


def test_04_pre_execution_reject(bridge):
    section("Test 04: pre_execution — reject flow (short-circuit)")
    bridge.clear()
    _reset_call_log()

    # Register a rejector then an approver — approver should NOT run
    bridge.register_pre_execution(pre_reject_dangerous, name="test.reject_dangerous")
    bridge.register_pre_execution(pre_approve_all, name="test.approve_all")

    dangerous_params = {"target_directory": "/etc/passwd", "remote_url": "https://example.com/repo.git"}
    decision = bridge.pre_execution(SKILL_META, dangerous_params)

    check("allow=False (rejected)", decision.allow is False)
    check("reason mentions handler name",
          "test.reject_dangerous" in decision.reason)
    check("reason mentions /etc",
          "/etc" in decision.reason or "系统目录" in decision.reason)
    check("second handler NOT called (short-circuit)",
          "pre_approve_all" not in _call_log)
    check("only first handler called",
          _call_log == ["pre_reject_dangerous"])


def test_05_pre_execution_modify_params(bridge):
    section("Test 05: pre_execution — parameter modification")
    bridge.clear()
    _reset_call_log()

    bridge.register_pre_execution(pre_inject_trace, name="test.inject_trace")
    bridge.register_pre_execution(pre_approve_all, name="test.approve_all")

    decision = bridge.pre_execution(SKILL_META, INPUT_PARAMS)

    check("allow=True", decision.allow is True)
    check("trace_id injected",
          decision.modified_params.get("_trace_id") == "trace-001")
    check("timestamp injected",
          decision.modified_params.get("_timestamp") == "2026-05-14T12:00:00Z")
    check("original params preserved",
          decision.modified_params.get("target_directory") == "/tmp/test-backup")
    check("both handlers called",
          _call_log == ["pre_inject_trace", "pre_approve_all"])


def test_06_post_execution_augmentation(bridge):
    section("Test 06: post_execution — augmentation flow")
    bridge.clear()
    _reset_call_log()

    bridge.register_post_execution(post_log_result, name="test.log_result")
    bridge.register_post_execution(post_add_metadata, name="test.add_metadata")

    result = bridge.post_execution(SKILL_META, EXEC_RESULT_SUCCESS, AUDIT_RECEIPT)

    check("logged=True", result.augmented.get("logged") is True)
    check("logger name correct",
          result.augmented.get("logger") == "post_log_result")
    check("processed_by set",
          result.augmented.get("processed_by") == "test-suite")
    check("both handlers called",
          _call_log == ["post_log_result", "post_add_metadata"])


def test_07_post_execution_handles_crash(bridge):
    section("Test 07: post_execution — handler crash does not break chain")
    bridge.clear()
    _reset_call_log()

    bridge.register_post_execution(post_log_result, name="test.log_result")
    bridge.register_post_execution(post_failing_handler, name="test.failing")
    bridge.register_post_execution(post_after_failing, name="test.after_failing")

    result = bridge.post_execution(SKILL_META, EXEC_RESULT_SUCCESS, AUDIT_RECEIPT)

    check("first handler ran", "post_log_result" in _call_log)
    check("failing handler was attempted", "post_failing_handler" in _call_log)
    check("handler after crash still ran", "post_after_failing" in _call_log)
    check("survived_crash=True",
          result.augmented.get("survived_crash") is True)
    check("logged still True (from first handler)",
          result.augmented.get("logged") is True)


def test_08_error_transient_retry(bridge):
    section("Test 08: error hook — transient error → retry")
    bridge.clear()
    _reset_call_log()

    bridge.register_error(error_detect_transient, name="test.transient")

    action = bridge.error(SKILL_META, ERROR_INFO_TRANSIENT)

    check("action=retry", action.action == "retry")
    check("reason mentions transient", "transient" in action.reason.lower() or "timeout" in action.reason.lower())
    check("handler called", "error_detect_transient" in _call_log)


def test_09_error_fatal_abort(bridge):
    section("Test 09: error hook — fatal error → abort")
    bridge.clear()
    _reset_call_log()

    bridge.register_error(error_detect_transient, name="test.transient")

    action = bridge.error(SKILL_META, ERROR_INFO_FATAL)

    check("action=abort", action.action == "abort")
    check("handler called", "error_detect_transient" in _call_log)


def test_10_error_chain(bridge):
    section("Test 10: error hook — chain with 'ignore' short-circuit")
    bridge.clear()
    _reset_call_log()

    # First handler: detect transient → retry
    bridge.register_error(error_detect_transient, name="test.transient")
    # Second handler: always says ignore (should stop chain)
    bridge.register_error(error_always_ignore, name="test.ignore")
    # Third handler: should NOT run
    bridge.register_error(error_escalate, name="test.escalate")

    action = bridge.error(SKILL_META, ERROR_INFO_TRANSIENT)

    check("action=ignore (second handler overrides first)",
          action.action == "ignore")
    check("first handler called", "error_detect_transient" in _call_log)
    check("second handler called", "error_always_ignore" in _call_log)
    check("third handler NOT called (ignore short-circuits)",
          "error_escalate" not in _call_log)


def test_11_config_file_loading():
    section("Test 11: Config file loading from JSON")
    bridge = PluginBridge()

    # Load the example config
    config_path = _SCRIPT_DIR / "plugin-config.example.json"
    bridge.load_config(str(config_path))

    h = bridge.registered_handlers
    check("pre_execution handlers loaded from config",
          len(h["pre_execution"]) >= 2)
    check("post_execution handlers loaded from config",
          len(h["post_execution"]) >= 1)
    check("error handlers loaded from config",
          len(h["error"]) >= 1)

    # Verify the handlers actually work
    decision = bridge.pre_execution(SKILL_META, INPUT_PARAMS)
    check("config-loaded pre_execution: approve", decision.allow is True)

    # Test with empty tools → should be rejected by builtin_permission_check
    bad_meta = dict(SKILL_META)
    bad_meta["permissions"] = {"tools": []}
    decision2 = bridge.pre_execution(bad_meta, INPUT_PARAMS)
    check("config-loaded pre_execution: reject empty tools", decision2.allow is False)

    bridge.clear()


def test_12_create_default_bridge():
    section("Test 12: create_default_bridge() with built-in handlers")
    bridge = create_default_bridge()

    h = bridge.registered_handlers
    check("2 built-in pre_execution handlers",
          len(h["pre_execution"]) == 2)
    check("1 built-in post_execution handler",
          len(h["post_execution"]) == 1)
    check("1 built-in error handler",
          len(h["error"]) == 1)

    # Test builtin_permission_check: empty tools → reject
    bad_meta = dict(SKILL_META)
    bad_meta["permissions"] = {"tools": []}
    decision = bridge.pre_execution(bad_meta, INPUT_PARAMS)
    check("builtin rejects empty tools", decision.allow is False)

    # Test builtin_cost_guard: CRITICAL → reject
    critical_meta = dict(SKILL_META)
    critical_meta["cost"] = {**SKILL_META["cost"], "api_cost_risk": "CRITICAL"}
    decision2 = bridge.pre_execution(critical_meta, INPUT_PARAMS)
    check("builtin rejects CRITICAL cost", decision2.allow is False)

    # Test normal: approve
    decision3 = bridge.pre_execution(SKILL_META, INPUT_PARAMS)
    check("builtin approves normal skill", decision3.allow is True)

    # Test error handler: transient → retry
    action = bridge.error(SKILL_META, ERROR_INFO_TRANSIENT)
    check("builtin error handler: retry on timeout", action.action == "retry")

    # Test error handler: fatal → abort
    action2 = bridge.error(SKILL_META, ERROR_INFO_FATAL)
    check("builtin error handler: abort on permission error",
          action2.action == "abort")

    bridge.clear()


def test_13_full_execution_flow():
    section("Test 13: Full simulated execution flow (pre → run → post → audit)")
    bridge = PluginBridge()

    # Register handlers
    bridge.register_pre_execution(pre_scope_check, name="test.scope_check")
    bridge.register_pre_execution(pre_inject_trace, name="test.inject_trace")
    bridge.register_post_execution(post_log_result, name="test.log_result")
    bridge.register_post_execution(post_add_metadata, name="test.add_metadata")

    # ---- Phase A: Pre-execution ----
    decision = bridge.pre_execution(SKILL_META, INPUT_PARAMS)
    check("pre: allow=True", decision.allow is True)
    check("pre: trace_id injected",
          decision.modified_params.get("_trace_id") == "trace-001")

    # ---- Phase B: Simulated execution ----
    # In real life this would be hermes-audit wrapping a command
    executed_params = decision.modified_params
    simulated_result = {
        "status": "success",
        "exit_code": 0,
        "stdout": json.dumps({"backup_id": "backup-20260514-120000", "commit_hash": "a1b2c3d"}),
        "stderr": "",
        "duration_ms": 1234,
    }
    check("exec: used modified params",
          executed_params.get("_trace_id") == "trace-001")
    check("exec: status=success",
          simulated_result["status"] == "success")

    # ---- Phase C: Post-execution ----
    augmented = bridge.post_execution(SKILL_META, simulated_result, AUDIT_RECEIPT)
    check("post: logged=True",
          augmented.augmented.get("logged") is True)
    check("post: processed_by set",
          augmented.augmented.get("processed_by") == "test-suite")

    # ---- Phase D: Audit receipt verification ----
    check("audit: receipt has signature",
          "signature" in AUDIT_RECEIPT and len(AUDIT_RECEIPT["signature"]) > 0)


def test_14_error_execution_flow():
    section("Test 14: Simulated error flow (pre → error hook)")
    bridge = PluginBridge()

    bridge.register_pre_execution(pre_approve_all, name="test.approve_all")
    bridge.register_error(error_detect_transient, name="test.transient")
    bridge.register_error(error_always_ignore, name="test.ignore")

    # Pre passes
    decision = bridge.pre_execution(SKILL_META, INPUT_PARAMS)
    check("pre: approved", decision.allow is True)

    # Simulate execution failure with transient error
    action = bridge.error(SKILL_META, ERROR_INFO_TRANSIENT)
    check("error: handler chain ran", True)
    check("error: first handler says retry (but overridden by ignore)",
          action.action == "ignore")

    # Now with fatal error and only transient detector
    bridge2 = PluginBridge()
    bridge2.register_error(error_detect_transient, name="test.transient")
    action2 = bridge2.error(SKILL_META, ERROR_INFO_FATAL)
    check("error: fatal → abort", action2.action == "abort")


def test_15_handler_ordering():
    section("Test 15: Handler execution order is registration order")
    bridge = PluginBridge()
    _reset_call_log()

    bridge.register_pre_execution(pre_approve_all, name="first")
    bridge.register_pre_execution(pre_inject_trace, name="second")
    bridge.register_pre_execution(pre_scope_check, name="third")

    bridge.pre_execution(SKILL_META, INPUT_PARAMS)

    check("order: first → second → third",
          _call_log == ["pre_approve_all", "pre_inject_trace", "pre_scope_check"])


def test_16_type_safety():
    section("Test 16: Registering a class instead of callable raises TypeError")
    bridge = PluginBridge()

    class BadHandler:
        pass

    caught = False
    try:
        bridge.register_pre_execution(BadHandler, name="bad")
    except TypeError:
        caught = True
    check("TypeError raised for class registration", caught)


def test_17_return_type_normalisation():
    section("Test 17: Handler return type normalisation (dict vs dataclass)")
    bridge = PluginBridge()

    # Handler returning a raw dict
    def dict_handler(skill_meta, input_params):
        return {"allow": True, "reason": "raw dict", "modified_params": {"key": "val"}}

    # Handler returning a dataclass
    def dc_handler(skill_meta, input_params):
        return PreExecutionDecision(allow=True, reason="dataclass", modified_params={"key2": "val2"})

    bridge.register_pre_execution(dict_handler, name="dict")
    bridge.register_pre_execution(dc_handler, name="dc")

    decision = bridge.pre_execution(SKILL_META, INPUT_PARAMS)
    check("allow=True (both approved)", decision.allow is True)
    check("dict handler params merged",
          decision.modified_params.get("key") == "val")
    check("dc handler params merged",
          decision.modified_params.get("key2") == "val2")


def test_18_empty_bridge_behaviour():
    section("Test 18: Bridge with no handlers — safe defaults")
    bridge = PluginBridge()

    # pre_execution: should approve (no rejections)
    decision = bridge.pre_execution(SKILL_META, INPUT_PARAMS)
    check("empty pre: allow=True", decision.allow is True)
    check("empty pre: no modified params", decision.modified_params == {})

    # post_execution: should return empty augmented
    result = bridge.post_execution(SKILL_META, EXEC_RESULT_SUCCESS, AUDIT_RECEIPT)
    check("empty post: augmented empty", result.augmented == {})

    # error: should default to abort
    action = bridge.error(SKILL_META, ERROR_INFO_FATAL)
    check("empty error: action=abort", action.action == "abort")


def test_19_unknown_config_section():
    section("Test 19: Unknown config section is gracefully skipped")
    import json, tempfile, os

    bad_config = {
        "pre_execution": [],
        "unknown_hook": [{"name": "x", "handler": "hermes_plugin_bridge:builtin_permission_check"}],
    }
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(bad_config, tmp)
    tmp.close()

    bridge = PluginBridge()
    bridge.load_config(tmp.name)
    # Should not crash
    h = bridge.registered_handlers
    check("unknown section skipped, no handlers registered",
          h["pre_execution"] == [] and h["post_execution"] == [] and h["error"] == [])

    os.unlink(tmp.name)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("  Hermes Plugin Bridge — End-to-End Test Suite")
    print("  Phase 4: Extension Guide + Plugin Bridge")
    print("=" * 70)

    bridge = test_01_import_and_instantiate()
    test_02_register_handlers(bridge)
    test_03_pre_execution_approve(bridge)
    test_04_pre_execution_reject(bridge)
    test_05_pre_execution_modify_params(bridge)
    test_06_post_execution_augmentation(bridge)
    test_07_post_execution_handles_crash(bridge)
    test_08_error_transient_retry(bridge)
    test_09_error_fatal_abort(bridge)
    test_10_error_chain(bridge)
    test_11_config_file_loading()
    test_12_create_default_bridge()
    test_13_full_execution_flow()
    test_14_error_execution_flow()
    test_15_handler_ordering()
    test_16_type_safety()
    test_17_return_type_normalisation()
    test_18_empty_bridge_behaviour()
    test_19_unknown_config_section()

    # Summary
    print(f"\n{'='*70}")
    total = PASS + FAIL
    print(f"  Results: {PASS}/{total} passed, {FAIL}/{total} failed")
    print(f"{'='*70}")

    if FAIL > 0:
        print(f"\n❌ {FAIL} test(s) FAILED — see details above.")
        sys.exit(1)
    else:
        print(f"\n✅ All {PASS} tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
