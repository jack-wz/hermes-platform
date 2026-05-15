#!/usr/bin/env python3
"""
hermes-dashboard — Web Dashboard + REST API for Hermes Workspace.

A single-file Flask app providing:
  - REST API: coworkers, skills, memory, status, execution logs
  - Web Dashboard (dark-themed, single-page, pure HTML+CSS)
  - Actual coworker execution via subprocess (not just log stubs!)

Usage:
    pip install flask pyyaml
    python3 build/workspace/hermes-dashboard.py
    # Opens at http://localhost:5002

Endpoints:
    GET  /api/coworkers          — list all coworkers
    POST /api/coworkers/run      — trigger a coworker (spawns subprocess)
    GET  /api/coworkers/<id>/log — recent execution logs
    GET  /api/registry/skills    — list registered skills
    GET  /api/memory             — get shared memory
    POST /api/memory             — add memory entry
    GET  /api/memory/context     — compressed context for coworker injection
    GET  /api/memory/namespaces  — list memory namespaces (v1.2)
    GET  /api/memory/gate-mem    — GateMem-compatible export (v1.2)
    GET  /api/status             — workspace health/status
    GET  /                       — web dashboard
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from flask import Flask, Response, jsonify, render_template_string, request

# ---------------------------------------------------------------------------
# Paths — resolved relative to this script
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent  # -> ~/.hermes/workspace
REGISTRY_COWORKERS = PROJECT_ROOT / "registry" / "coworkers.json"
REGISTRY_SKILLS = PROJECT_ROOT / "registry" / "skills.json"
SHARED_MEMORY_FILE = PROJECT_ROOT / "SHARED_MEMORY.md"
LOGS_DIR = PROJECT_ROOT / "logs" / "coworkers"
COWORKER_ENGINE_SCRIPT = SCRIPT_DIR / "hermes-coworker.py"
MEMORY_SCRIPT = SCRIPT_DIR / "hermes-memory.py"
KANBAN_DB = Path.home() / ".hermes" / "kanban.db"

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MEMORY_ENTRY_RE = re.compile(
    r"^##\s+\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\]\s+(.+?)\s*$"
)


def _load_json(path: Path) -> dict:
    """Load a JSON file, returning empty dict on failure."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _parse_memory_entries() -> list[dict]:
    """Parse SHARED_MEMORY.md into a list of structured entries."""
    if not SHARED_MEMORY_FILE.exists():
        return []
    lines = SHARED_MEMORY_FILE.read_text(encoding="utf-8").split("\n")
    entries: list[dict] = []
    current: Optional[dict] = None
    for line in lines:
        m = MEMORY_ENTRY_RE.match(line)
        if m:
            if current is not None:
                current["body"] = "\n".join(current.pop("_body_lines")).strip()
                entries.append(current)
            current = {
                "timestamp": m.group(1),
                "author": m.group(2).strip(),
                "_body_lines": [],
            }
        elif current is not None:
            current["_body_lines"].append(line)
    if current is not None:
        current["body"] = "\n".join(current.pop("_body_lines")).strip()
        entries.append(current)
    return entries


def _load_execution_logs(limit: int = 20) -> list[dict]:
    """Load recent execution logs from logs/coworkers/."""
    if not LOGS_DIR.exists():
        return []
    log_files = sorted(
        LOGS_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    logs = []
    for lf in log_files[:limit]:
        try:
            data = json.loads(lf.read_text(encoding="utf-8"))
            logs.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    # Sort by started_at descending
    logs.sort(key=lambda x: x.get("started_at", ""), reverse=True)
    return logs[:limit]


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.route("/api/coworkers", methods=["GET"])
def api_coworkers():
    """List all registered coworkers."""
    reg = _load_json(REGISTRY_COWORKERS)
    coworkers = reg.get("coworkers", [])
    return jsonify({
        "success": True,
        "count": len(coworkers),
        "coworkers": coworkers,
    })


@app.route("/api/coworkers/run", methods=["POST"])
def api_coworkers_run():
    """Trigger a coworker execution — spawns hermes-coworker.py as subprocess."""
    body = request.get_json(silent=True) or {}
    coworker_id = body.get("coworker_id", "").strip()
    if not coworker_id:
        return jsonify({"success": False, "error": "Missing 'coworker_id'"}), 400

    reg = _load_json(REGISTRY_COWORKERS)
    coworker = None
    for c in reg.get("coworkers", []):
        if c["coworker_id"] == coworker_id:
            coworker = c
            break
    if not coworker:
        return jsonify({"success": False, "error": f"Coworker not found: {coworker_id}"}), 404

    run_id = uuid.uuid4().hex[:8]
    started = datetime.now(timezone.utc)

    # Pre-create log entry
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = coworker_id.replace("/", "_")
    log_path = LOGS_DIR / f"{safe_id}_{run_id}.json"

    run_log = {
        "run_id": run_id,
        "coworker_id": coworker_id,
        "run_name": coworker.get("name", coworker_id),
        "trigger_reason": "api",
        "started_at": started.isoformat(),
        "completed_at": None,
        "duration_ms": None,
        "exit_code": None,
        "stdout": "",
        "stderr": "",
        "results": [
            {"skill_id": sid, "status": "pending", "note": "Spawned via dashboard API"}
            for sid in coworker.get("skills", [])
        ],
    }

    def _run_coworker():
        """Background thread: execute hermes-coworker.py and update log."""
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(COWORKER_ENGINE_SCRIPT),
                    "run", coworker_id,
                ],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(PROJECT_ROOT),
            )
            stdout = proc.stdout[-8000:] if len(proc.stdout) > 8000 else proc.stdout
            stderr = proc.stderr[-4000:] if len(proc.stderr) > 4000 else proc.stderr
            run_log["completed_at"] = datetime.now(timezone.utc).isoformat()
            run_log["duration_ms"] = int(
                (datetime.now(timezone.utc) - started).total_seconds() * 1000
            )
            run_log["exit_code"] = proc.returncode
            run_log["stdout"] = stdout
            run_log["stderr"] = stderr
            for r in run_log["results"]:
                r["status"] = "completed" if proc.returncode == 0 else "error"
        except subprocess.TimeoutExpired:
            run_log["completed_at"] = datetime.now(timezone.utc).isoformat()
            run_log["duration_ms"] = 120_000
            run_log["exit_code"] = -1
            run_log["stderr"] = "Coworker execution timed out (120s)"
            for r in run_log["results"]:
                r["status"] = "timeout"
        except Exception as exc:
            run_log["completed_at"] = datetime.now(timezone.utc).isoformat()
            run_log["duration_ms"] = int(
                (datetime.now(timezone.utc) - started).total_seconds() * 1000
            )
            run_log["exit_code"] = -2
            run_log["stderr"] = f"Subprocess error: {exc}"
            for r in run_log["results"]:
                r["status"] = "error"
        finally:
            log_path.write_text(
                json.dumps(run_log, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    # Spawn background thread — returns immediately
    t = threading.Thread(target=_run_coworker, daemon=True)
    t.start()

    # Write initial log (completed_at=None signals "in progress")
    log_path.write_text(
        json.dumps(run_log, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return jsonify({
        "success": True,
        "run_id": run_id,
        "status": "dispatched",
        "coworker_id": coworker_id,
        "skills_count": len(coworker.get("skills", [])),
    })


@app.route("/api/coworkers/<path:coworker_id>/log", methods=["GET"])
def api_coworkers_log(coworker_id: str):
    """Get recent execution logs for a specific coworker."""
    if not LOGS_DIR.exists():
        return jsonify({"success": True, "coworker_id": coworker_id, "logs": []})

    safe_id = coworker_id.replace("/", "_")
    log_files = sorted(
        LOGS_DIR.glob(f"{safe_id}_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    logs = []
    for lf in log_files[:10]:
        try:
            data = json.loads(lf.read_text(encoding="utf-8"))
            logs.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return jsonify({"success": True, "coworker_id": coworker_id, "logs": logs})


@app.route("/api/registry/skills", methods=["GET"])
def api_registry_skills():
    """List all registered skills."""
    reg = _load_json(REGISTRY_SKILLS)
    skills = reg.get("skills", [])
    return jsonify({
        "success": True,
        "count": len(skills),
        "skills": skills,
    })


@app.route("/api/memory", methods=["GET"])
def api_memory_get():
    """Get all shared memory entries."""
    entries = _parse_memory_entries()
    return jsonify({
        "success": True,
        "count": len(entries),
        "entries": entries,
        "raw": SHARED_MEMORY_FILE.read_text(encoding="utf-8") if SHARED_MEMORY_FILE.exists() else "",
    })


@app.route("/api/memory", methods=["POST"])
def api_memory_post():
    """Add a memory entry."""
    body = request.get_json(silent=True) or {}
    entry_text = body.get("entry", "").strip()
    author = body.get("author", "api").strip()
    if not entry_text:
        return jsonify({"success": False, "error": "Missing 'entry'"}), 400

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    header = f"## [{timestamp}] {author}"
    entry_block = header + "\n" + entry_text + "\n"

    if not SHARED_MEMORY_FILE.exists():
        SHARED_MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        SHARED_MEMORY_FILE.write_text(
            "# Team Shared Memory\n\n"
            "> 纠正一个 Agent 犯的错，团队里所有 Agent 都记住了。\n"
            "> Correct one agent's mistake, ALL agents remember it.\n\n",
            encoding="utf-8",
        )
    with open(SHARED_MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write("\n" + entry_block)

    return jsonify({
        "success": True,
        "timestamp": timestamp,
        "author": author,
        "entry": entry_text,
    })


@app.route("/api/memory/context", methods=["GET"])
def api_memory_context():
    """Return compressed shared-memory context for coworker prompt injection."""
    entries = _parse_memory_entries()
    # Return last 10 entries only (compressed context)
    recent = entries[-10:] if len(entries) > 10 else entries
    lines = []
    for e in recent:
        lines.append(
            f"[{e.get('timestamp', '')}] [{e.get('author', '')}]\n"
            f"{e.get('body', '')[:500]}"  # Truncate long entries
        )
    return jsonify({
        "success": True,
        "entry_count": len(entries),
        "recent_entries": len(recent),
        "context": "\n\n".join(lines),
    })


@app.route("/api/memory/namespaces", methods=["GET"])
def api_memory_namespaces():
    """List available memory namespaces and their entry counts (v1.2)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "hermes_memory", SCRIPT_DIR / "hermes-memory.py"
    )
    mem_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mem_module)
    mem = mem_module.SharedMemory()
    namespaces = mem.list_namespaces()
    # Enrich with entry counts
    for ns in namespaces:
        entries = mem.get_namespace_entries(ns["id"])
        ns["entry_count"] = len(entries)
    return jsonify({
        "success": True,
        "count": len(namespaces),
        "namespaces": namespaces,
    })


@app.route("/api/memory/gate-mem", methods=["GET"])
def api_memory_gate_mem():
    """Export memory in GateMem-compatible format (v1.2)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "hermes_memory", SCRIPT_DIR / "hermes-memory.py"
    )
    mem_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mem_module)
    mem = mem_module.SharedMemory()
    export = mem.gate_mem_compat_export()
    return jsonify({"success": True, **export})


@app.route("/api/status", methods=["GET"])
def api_status():
    """Workspace health/status."""
    coworker_reg = _load_json(REGISTRY_COWORKERS)
    skills_reg = _load_json(REGISTRY_SKILLS)
    coworkers = coworker_reg.get("coworkers", [])
    skills = skills_reg.get("skills", [])
    memory_entries = _parse_memory_entries()
    logs = _load_execution_logs(limit=50)

    active_coworkers = sum(1 for c in coworkers if c.get("status") == "active")
    verified_skills = sum(1 for s in skills if s.get("status") == "verified")

    return jsonify({
        "success": True,
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "coworkers_total": len(coworkers),
            "coworkers_active": active_coworkers,
            "skills_total": len(skills),
            "skills_verified": verified_skills,
            "memory_entries": len(memory_entries),
            "execution_logs": len(logs),
        },
        "registry_updated": coworker_reg.get("updated_at", ""),
    })


@app.route("/api/activity", methods=["GET"])
def api_activity():
    """Get recent activity feed from execution logs."""
    logs = _load_execution_logs(limit=5)
    return jsonify({"success": True, "count": len(logs), "activity": logs})


# ---------------------------------------------------------------------------
# Kanban API — reads from ~/.hermes/kanban.db (Hermes kernel-managed SQLite)
# ---------------------------------------------------------------------------

def _kanban_conn():
    """Get a connection to the kanban database with WAL mode for concurrent reads."""
    import sqlite3
    conn = sqlite3.connect(str(KANBAN_DB), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
    return conn


def _row_to_dict(row):
    """Convert sqlite3.Row to plain dict with camelCase keys."""
    if row is None:
        return {}
    d = dict(row)
    key_map = {
        "created_at": "createdAt", "started_at": "startedAt",
        "completed_at": "completedAt", "created_by": "createdBy",
        "workspace_kind": "workspaceKind", "workspace_path": "workspacePath",
        "claim_lock": "claimLock", "claim_expires": "claimExpires",
        "idempotency_key": "idempotencyKey", "consecutive_failures": "consecutiveFailures",
        "worker_pid": "workerPid", "last_failure_error": "lastFailureError",
        "max_runtime_seconds": "maxRuntimeSeconds", "last_heartbeat_at": "lastHeartbeatAt",
        "current_run_id": "currentRunId", "workflow_template_id": "workflowTemplateId",
        "current_step_key": "currentStepKey", "max_retries": "maxRetries",
    }
    result = {}
    for k, v in d.items():
        new_key = key_map.get(k, k)
        result[new_key] = v
    return result


@app.route("/api/kanban/tasks", methods=["GET"])
def api_kanban_tasks():
    """List all kanban tasks, grouped by status column."""
    status_filter = request.args.get("status", "")
    assignee_filter = request.args.get("assignee", "")
    try:
        conn = _kanban_conn()
        cur = conn.cursor()
        query = "SELECT id, title, assignee, status, priority, created_at, workspace_kind FROM tasks"
        params = []
        conditions = []
        if status_filter:
            conditions.append("status = ?")
            params.append(status_filter)
        if assignee_filter:
            conditions.append("assignee = ?")
            params.append(assignee_filter)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY priority DESC, created_at DESC"
        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()
        tasks = [_row_to_dict(r) for r in rows]
        columns = {
            "todo": [], "ready": [], "in_progress": [], "blocked": [], "done": [], "archived": []
        }
        # Map alternate status values to canonical columns
        status_map = {"running": "in_progress"}
        for t in tasks:
            col = t.get("status", "todo")
            col = status_map.get(col, col)
            if col not in columns:
                col = "todo"
            columns[col].append(t)
        return jsonify({
            "success": True,
            "total": len(tasks),
            "columns": columns,
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/kanban/tasks/<task_id>", methods=["GET"])
def api_kanban_task_detail(task_id):
    """Get a single kanban task with comments and events."""
    try:
        conn = _kanban_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({"success": False, "error": "Task not found"}), 404
        task = _row_to_dict(row)
        cur.execute(
            "SELECT * FROM task_comments WHERE task_id = ? ORDER BY created_at ASC",
            (task_id,))
        comments = [_row_to_dict(r) for r in cur.fetchall()]
        cur.execute(
            "SELECT * FROM task_events WHERE task_id = ? ORDER BY created_at DESC LIMIT 20",
            (task_id,))
        events = [_row_to_dict(r) for r in cur.fetchall()]
        conn.close()
        return jsonify({
            "success": True,
            "task": task,
            "comments": comments,
            "events": events,
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/kanban/stats", methods=["GET"])
def api_kanban_stats():
    """Get kanban board statistics."""
    try:
        conn = _kanban_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT status, COUNT(*) as cnt FROM tasks
            WHERE status != 'archived'
            GROUP BY status
        """)
        rows = cur.fetchall()
        conn.close()
        stats = {row["status"]: row["cnt"] for row in rows}
        total = sum(stats.values())
        return jsonify({
            "success": True,
            "total": total,
            "byStatus": stats,
            "columns": {
                "todo": stats.get("todo", 0),
                "ready": stats.get("ready", 0),
                "in_progress": stats.get("in_progress", 0),
                "blocked": stats.get("blocked", 0),
                "done": stats.get("done", 0),
            },
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Kanban Write API — create, update, move tasks
# ---------------------------------------------------------------------------

@app.route("/api/kanban/tasks", methods=["POST"])
def api_kanban_create():
    """Create a new kanban task."""
    try:
        data = request.get_json(force=True)
        title = data.get("title", "").strip()
        if not title:
            return jsonify({"success": False, "error": "title is required"}), 400

        import uuid
        task_id = data.get("id") or f"t-{uuid.uuid4().hex[:8]}"
        description = data.get("description", "")
        assignee = data.get("assignee", "")
        status = data.get("status", "todo")
        priority = data.get("priority", 2)
        board = data.get("board", "execution")
        workspace_kind = data.get("workspaceKind", "")
        created_by = data.get("createdBy", "api")
        now = datetime.utcnow().isoformat()

        conn = _kanban_conn()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO tasks (id, title, description, assignee, status, priority, board,
               workspace_kind, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, title, description, assignee, status, priority, board,
             workspace_kind, created_by, now, now),
        )
        # Creation event
        cur.execute(
            "INSERT INTO task_events (task_id, event_type, new_value, created_by, created_at) "
            "VALUES (?, 'created', ?, ?, ?)",
            (task_id, status, created_by, now),
        )
        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "task": {"id": task_id, "title": title, "status": status},
        }), 201
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/kanban/tasks/<task_id>", methods=["PATCH"])
def api_kanban_update(task_id):
    """Update a kanban task — status, assignee, priority, title, description."""
    try:
        data = request.get_json(force=True)
        conn = _kanban_conn()
        cur = conn.cursor()

        # Verify task exists
        cur.execute("SELECT id, status, assignee FROM tasks WHERE id = ?", (task_id,))
        existing = cur.fetchone()
        if not existing:
            conn.close()
            return jsonify({"success": False, "error": "Task not found"}), 404

        old_status = existing["status"]
        old_assignee = existing["assignee"]
        now = datetime.utcnow().isoformat()
        updates = []
        params = []
        events = []

        # Status change
        if "status" in data:
            new_status = data["status"]
            updates.append("status = ?")
            params.append(new_status)
            if new_status != old_status:
                if new_status == "in_progress" and not existing["started_at"]:
                    updates.append("started_at = ?")
                    params.append(now)
                if new_status == "done":
                    updates.append("completed_at = ?")
                    params.append(now)
                events.append(("status_change", old_status, new_status))

        # Assignee change
        if "assignee" in data:
            new_assignee = data["assignee"]
            updates.append("assignee = ?")
            params.append(new_assignee)
            if new_assignee != old_assignee:
                events.append(("assignee_change", old_assignee, new_assignee))

        # Priority change
        if "priority" in data:
            updates.append("priority = ?")
            params.append(data["priority"])
            events.append(("priority_change", str(existing.get("priority", "")), str(data["priority"])))

        # Title / description
        for field in ["title", "description"]:
            if field in data:
                updates.append(f"{field} = ?")
                params.append(data[field])

        if not updates:
            conn.close()
            return jsonify({"success": False, "error": "No fields to update"}), 400

        updates.append("updated_at = ?")
        params.append(now)
        params.append(task_id)

        cur.execute(
            f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?",
            params,
        )

        # Record events
        for evt in events:
            cur.execute(
                "INSERT INTO task_events (task_id, event_type, old_value, new_value, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (task_id, evt[0], evt[1], evt[2], now),
            )

        conn.commit()

        # Return updated task
        cur.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task = _row_to_dict(cur.fetchone())
        conn.close()

        return jsonify({"success": True, "task": task})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/kanban/tasks/<task_id>/comments", methods=["POST"])
def api_kanban_add_comment(task_id):
    """Add a comment to a kanban task."""
    try:
        data = request.get_json(force=True)
        body = data.get("body", "").strip()
        if not body:
            return jsonify({"success": False, "error": "body is required"}), 400

        author = data.get("author", "api")
        now = datetime.utcnow().isoformat()

        conn = _kanban_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, ?, ?, ?)",
            (task_id, author, body, now),
        )
        conn.commit()
        comment_id = cur.lastrowid
        conn.close()

        return jsonify({
            "success": True,
            "comment": {"id": comment_id, "task_id": task_id, "author": author, "body": body},
        }), 201
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Web Dashboard (single HTML page)
# ---------------------------------------------------------------------------

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hermes Workspace</title>
<style>
  :root {
    --bg: #0d1117;
    --bg-card: #161b22;
    --bg-card-hover: #1c2333;
    --border: #30363d;
    --text: #c9d1d9;
    --text-muted: #8b949e;
    --accent: #3fb950;
    --accent-dim: #2ea043;
    --red: #f85149;
    --yellow: #d2991d;
    --blue: #58a6ff;
    --purple: #bc8cff;
    --radius: 8px;
    --shadow: 0 1px 3px rgba(0,0,0,.3);
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    min-height: 100vh;
  }
  a { color: var(--blue); text-decoration: none; }
  a:hover { text-decoration: underline; }

  /* Header */
  .header {
    background: var(--bg-card);
    border-bottom: 1px solid var(--border);
    padding: 16px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
    position: sticky; top: 0; z-index: 10;
  }
  .header-left { display: flex; align-items: center; gap: 12px; }
  .header-logo {
    width: 36px; height: 36px;
    background: linear-gradient(135deg, var(--accent), #1a7f37);
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px; font-weight: 700; color: #fff;
  }
  .header h1 { font-size: 20px; font-weight: 600; }
  .status-badge {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 12px; border-radius: 20px;
    font-size: 12px; font-weight: 600;
    background: rgba(63,185,80,.15); color: var(--accent);
    border: 1px solid rgba(63,185,80,.3);
  }
  .status-dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
  .header-actions { display: flex; gap: 8px; flex-wrap: wrap; }

  /* Buttons */
  .btn {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 6px 14px; border-radius: 6px;
    font-size: 13px; font-weight: 500; cursor: pointer;
    border: 1px solid var(--border);
    background: var(--bg-card); color: var(--text);
    transition: all .15s;
  }
  .btn:hover { background: var(--bg-card-hover); border-color: var(--accent-dim); }
  .btn-accent { background: var(--accent-dim); color: #fff; border-color: var(--accent-dim); }
  .btn-accent:hover { background: var(--accent); }
  .btn-sm { padding: 4px 10px; font-size: 12px; }

  /* Layout */
  .container { max-width: 1300px; margin: 0 auto; padding: 24px; }
  .grid { display: grid; gap: 20px; }
  .grid-2 { grid-template-columns: 1fr 1fr; }
  .grid-3 { grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }

  /* Cards */
  .card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    box-shadow: var(--shadow);
    transition: border-color .15s;
  }
  .card:hover { border-color: var(--accent-dim); }
  .card-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 16px; padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
  }
  .card-title { font-size: 15px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
  .card-title .icon { font-size: 18px; }
  .card-full { grid-column: 1 / -1; }

  /* Stats row */
  .stats-row { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }
  .stat-box {
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 16px 20px;
    flex: 1; min-width: 140px;
    display: flex; flex-direction: column; gap: 4px;
  }
  .stat-value { font-size: 28px; font-weight: 700; color: var(--accent); }
  .stat-label { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: .5px; }

  /* Coworker cards */
  .coworker-card {
    display: flex; flex-direction: column; gap: 10px;
  }
  .coworker-name {
    font-size: 15px; font-weight: 600;
    display: flex; align-items: center; gap: 8px;
  }
  .coworker-role {
    display: inline-block; padding: 2px 8px; border-radius: 12px;
    font-size: 11px; font-weight: 500;
    background: rgba(88,166,255,.15); color: var(--blue);
    border: 1px solid rgba(88,166,255,.25);
  }
  .coworker-role.ops { background: rgba(63,185,80,.15); color: var(--accent); border-color: rgba(63,185,80,.25); }
  .coworker-role.sales { background: rgba(188,140,255,.15); color: var(--purple); border-color: rgba(188,140,255,.25); }
  .coworker-role.marketing { background: rgba(210,153,29,.15); color: var(--yellow); border-color: rgba(210,153,29,.25); }
  .coworker-role.legal { background: rgba(248,81,73,.15); color: var(--red); border-color: rgba(248,81,73,.25); }
  .coworker-role.hr { background: rgba(88,166,255,.15); color: var(--blue); border-color: rgba(88,166,255,.25); }
  .coworker-id { font-size: 12px; color: var(--text-muted); font-family: monospace; }
  .coworker-desc { font-size: 13px; color: var(--text-muted); line-height: 1.5; }
  .coworker-meta {
    display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
    margin-top: auto; padding-top: 8px; border-top: 1px solid var(--border);
  }
  .coworker-meta-item {
    font-size: 11px; color: var(--text-muted);
    display: flex; align-items: center; gap: 4px;
  }
  .schedule-tag {
    font-family: monospace; font-size: 11px;
    padding: 2px 6px; border-radius: 4px;
    background: rgba(139,148,158,.1); color: var(--text-muted);
  }
  .active-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
  .active-dot.on { background: var(--accent); }
  .active-dot.off { background: var(--text-muted); }

  /* Activity feed */
  .activity-item {
    display: flex; gap: 12px; padding: 10px 0;
    border-bottom: 1px solid var(--border);
  }
  .activity-item:last-child { border-bottom: none; }
  .activity-dot {
    width: 10px; height: 10px; border-radius: 50%;
    background: var(--accent); margin-top: 4px; flex-shrink: 0;
  }
  .activity-info { flex: 1; min-width: 0; }
  .activity-title { font-size: 13px; font-weight: 500; }
  .activity-meta { font-size: 11px; color: var(--text-muted); }
  .activity-status {
    font-size: 11px; padding: 1px 6px; border-radius: 4px;
    font-weight: 500;
  }
  .activity-status.success { background: rgba(63,185,80,.15); color: var(--accent); }
  .activity-status.error { background: rgba(248,81,73,.15); color: var(--red); }

  /* Memory panel */
  .memory-item {
    padding: 10px 0; border-bottom: 1px solid var(--border);
  }
  .memory-item:last-child { border-bottom: none; }
  .memory-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 4px;
  }
  .memory-author { font-size: 12px; font-weight: 600; }
  .memory-author.human { color: var(--yellow); }
  .memory-time { font-size: 11px; color: var(--text-muted); }
  .memory-body { font-size: 13px; color: var(--text-muted); line-height: 1.5; white-space: pre-wrap; }

  /* Empty state */
  .empty { color: var(--text-muted); font-size: 13px; text-align: center; padding: 20px; }

  /* Toast */
  .toast {
    position: fixed; bottom: 24px; right: 24px;
    padding: 12px 20px; border-radius: var(--radius);
    background: var(--bg-card); border: 1px solid var(--border);
    color: var(--text); font-size: 13px;
    box-shadow: 0 4px 12px rgba(0,0,0,.4);
    z-index: 100; opacity: 0; transform: translateY(10px);
    transition: opacity .2s, transform .2s;
  }
  .toast.show { opacity: 1; transform: translateY(0); }
  .toast.success { border-color: var(--accent); }
  .toast.error { border-color: var(--red); }

  /* Modal */
  .modal-overlay {
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,.6); z-index: 50;
    align-items: center; justify-content: center;
  }
  .modal-overlay.open { display: flex; }
  .modal {
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 24px;
    width: 90%; max-width: 480px; box-shadow: 0 8px 24px rgba(0,0,0,.5);
  }
  .modal h3 { font-size: 16px; margin-bottom: 16px; }
  .modal textarea, .modal input {
    width: 100%; padding: 10px; border-radius: 6px;
    border: 1px solid var(--border); background: var(--bg);
    color: var(--text); font-family: inherit; font-size: 13px;
    margin-bottom: 12px; resize: vertical;
  }
  .modal textarea { min-height: 100px; }
  .modal-actions { display: flex; gap: 8px; justify-content: flex-end; }

  /* Responsive */
  /* Kanban Board */
  .kanban-board {
    display: flex; gap: 12px; overflow-x: auto;
    padding: 8px 0; min-height: 200px;
  }
  .kanban-column {
    flex: 1; min-width: 180px; max-width: 280px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    display: flex; flex-direction: column;
  }
  .kanban-col-header {
    padding: 10px 12px; font-size: 12px; font-weight: 600;
    text-transform: uppercase; letter-spacing: .5px;
    border-bottom: 1px solid var(--border);
    display: flex; justify-content: space-between; align-items: center;
  }
  .kanban-col-header .count {
    font-size: 11px; color: var(--text-muted);
    background: var(--bg-card); padding: 1px 6px; border-radius: 10px;
  }
  .kanban-col-todo .kanban-col-header { color: var(--text-muted); }
  .kanban-col-ready .kanban-col-header { color: var(--blue); }
  .kanban-col-progress .kanban-col-header { color: var(--yellow); }
  .kanban-col-blocked .kanban-col-header { color: var(--red); }
  .kanban-col-done .kanban-col-header { color: var(--accent); }
  .kanban-cards {
    padding: 8px; display: flex; flex-direction: column; gap: 6px;
    flex: 1; overflow-y: auto; max-height: 400px;
  }
  .kanban-card {
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 6px; padding: 10px; cursor: pointer;
    transition: border-color .15s;
    font-size: 12px; line-height: 1.5;
  }
  .kanban-card:hover { border-color: var(--accent-dim); }
  .kanban-card-title {
    font-weight: 600; margin-bottom: 4px;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .kanban-card-meta {
    font-size: 11px; color: var(--text-muted);
    display: flex; justify-content: space-between; align-items: center;
    margin-top: 6px; padding-top: 6px; border-top: 1px solid var(--border);
  }
  .kanban-card-assignee {
    padding: 1px 6px; border-radius: 4px;
    background: rgba(88,166,255,.1); color: var(--blue);
    font-size: 10px;
  }
  .kanban-card-priority { font-weight: 600; }
  .kanban-card-priority.p0 { color: var(--red); }
  .kanban-card-priority.p1 { color: var(--yellow); }
  .kanban-card-priority.p2 { color: var(--text-muted); }

  /* Kanban detail drawer */
  .kanban-drawer {
    position: fixed; top: 0; right: 0; width: 380px; height: 100vh;
    background: var(--bg-card); border-left: 1px solid var(--border);
    z-index: 60; transform: translateX(100%);
    transition: transform .2s ease;
    padding: 20px; overflow-y: auto;
    box-shadow: -4px 0 16px rgba(0,0,0,.4);
  }
  .kanban-drawer.open { transform: translateX(0); }
  .kanban-drawer h3 { font-size: 16px; margin-bottom: 12px; }
  .kanban-drawer .close-btn {
    position: absolute; top: 12px; right: 16px;
    background: none; border: none; color: var(--text-muted);
    font-size: 20px; cursor: pointer;
  }
  .kanban-drawer .close-btn:hover { color: var(--text); }
  .kanban-detail-row { margin-bottom: 12px; }
  .kanban-detail-label { font-size: 11px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 2px; }
  .kanban-detail-value { font-size: 13px; }
  .kanban-detail-body {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 6px; padding: 10px;
    font-size: 12px; line-height: 1.6; white-space: pre-wrap;
    max-height: 200px; overflow-y: auto;
    font-family: monospace; color: var(--text-muted);
  }

  @media (max-width: 768px) {
    .grid-2 { grid-template-columns: 1fr; }
    .container { padding: 16px; }
    .header { padding: 12px 16px; }
    .kanban-board { flex-direction: column; }
    .kanban-column { max-width: none; min-width: 0; }
    .kanban-drawer { width: 100vw; }
  }
</style>
</head>
<body>

<!-- Header -->
<header class="header">
  <div class="header-left">
    <div class="header-logo">⚡</div>
    <h1>Hermes Workspace</h1>
    <span class="status-badge"><span class="status-dot"></span> Live</span>
  </div>
  <div class="header-actions" id="header-actions">
    <button class="btn btn-accent btn-sm" onclick="quickRunMorningBrief()" title="Trigger morning-brief coworker">☀️ Run Morning Brief</button>
    <button class="btn btn-sm" onclick="openAddMemory()">💬 Add Memory</button>
    <button class="btn btn-sm" onclick="openViewRegistry()">📋 Registry</button>
  </div>
</header>

<main class="container">

<!-- Stats Row -->
<div class="stats-row" id="stats-row">
  <div class="stat-box"><span class="stat-value" id="stat-coworkers">-</span><span class="stat-label">AI Coworkers</span></div>
  <div class="stat-box"><span class="stat-value" id="stat-skills">-</span><span class="stat-label">Skills</span></div>
  <div class="stat-box"><span class="stat-value" id="stat-memory">-</span><span class="stat-label">Memory Entries</span></div>
  <div class="stat-box"><span class="stat-value" id="stat-logs">-</span><span class="stat-label">Executions</span></div>
  <div class="stat-box"><span class="stat-value" id="stat-kanban">-</span><span class="stat-label">Kanban Tasks</span></div>
</div>

<div class="grid grid-2">

  <!-- AI Coworkers Panel -->
  <div class="card card-full">
    <div class="card-header">
      <span class="card-title"><span class="icon">🤖</span>AI Coworkers</span>
      <span class="schedule-tag" id="coworker-count">8 registered</span>
    </div>
    <div class="grid grid-3" id="coworkers-grid">
      <div class="empty">Loading coworkers...</div>
    </div>
  </div>

  <!-- Recent Activity -->
  <div class="card">
    <div class="card-header">
      <span class="card-title"><span class="icon">📊</span>Recent Activity</span>
    </div>
    <div id="activity-feed"><div class="empty">Loading activity...</div></div>
  </div>

  <!-- Shared Memory -->
  <div class="card">
    <div class="card-header">
      <span class="card-title"><span class="icon">🧠</span>Shared Memory</span>
      <span class="schedule-tag" id="memory-count">-</span>
    </div>
    <div id="memory-panel"><div class="empty">Loading memory...</div></div>
  </div>

  <!-- Kanban Board -->
  <div class="card card-full">
    <div class="card-header">
      <span class="card-title"><span class="icon">📋</span>Kanban Board</span>
      <span class="schedule-tag" id="kanban-count">0 tasks</span>
    </div>
    <div class="kanban-board" id="kanban-board">
      <div class="empty" style="grid-column:1/-1">Loading kanban...</div>
    </div>
  </div>

</div>
</main>

<!-- Add Memory Modal -->
<div class="modal-overlay" id="modal-memory">
  <div class="modal">
    <h3>💬 Add Shared Memory</h3>
    <input type="text" id="mem-author" placeholder="Author (e.g., human:CEO)" value="dashboard">
    <textarea id="mem-entry" placeholder="Memory entry text..."></textarea>
    <div class="modal-actions">
      <button class="btn" onclick="closeModal('modal-memory')">Cancel</button>
      <button class="btn btn-accent" onclick="submitMemory()">Save</button>
    </div>
  </div>
</div>

<!-- View Registry Modal -->
<div class="modal-overlay" id="modal-registry">
  <div class="modal" style="max-width: 640px;">
    <h3>📋 Skill Registry</h3>
    <div id="registry-content"></div>
    <div class="modal-actions">
      <button class="btn" onclick="closeModal('modal-registry')">Close</button>
    </div>
  </div>
</div>

<!-- Toast -->
<div class="toast" id="toast"></div>

<!-- Kanban Task Detail Drawer -->
<div class="kanban-drawer" id="kanban-drawer">
  <button class="close-btn" onclick="closeKanbanDrawer()">&times;</button>
  <div id="kanban-detail-content"></div>
</div>

<script>
// ---------------------------------------------------------------------------
// Dashboard logic (vanilla JS, no framework)
// ---------------------------------------------------------------------------

const API = '/api';

function showToast(msg, type) {
  var t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast ' + (type || '') + ' show';
  setTimeout(function(){ t.className = 'toast'; }, 3000);
}

function openModal(id) { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }

// ---- Load all data ----
function loadDashboard() {
  loadStatus();
  loadCoworkers();
  loadActivity();
  loadMemory();
  loadKanban();
}

function loadStatus() {
  fetch(API + '/status')
    .then(function(r){ return r.json(); })
    .then(function(d){
      document.getElementById('stat-coworkers').textContent = d.stats.coworkers_active + '/' + d.stats.coworkers_total;
      document.getElementById('stat-skills').textContent = d.stats.skills_total;
      document.getElementById('stat-memory').textContent = d.stats.memory_entries;
      document.getElementById('stat-logs').textContent = d.stats.execution_logs;
      loadKanbanStats();
    })
    .catch(function(){});
}

function loadCoworkers() {
  fetch(API + '/coworkers')
    .then(function(r){ return r.json(); })
    .then(function(d){
      var grid = document.getElementById('coworkers-grid');
      document.getElementById('coworker-count').textContent = d.count + ' registered';
      if (!d.coworkers.length) {
        grid.innerHTML = '<div class="empty">No coworkers registered</div>';
        return;
      }
      var roleClass = {operations:'ops',sales:'sales',marketing:'marketing',legal:'legal',hr:'hr',general:''};
      var roleEmoji = {operations:'⚙️',sales:'💼',marketing:'📣',legal:'⚖️',hr:'👥',general:'🤖'};
      grid.innerHTML = d.coworkers.map(function(c){
        var rc = roleClass[c.role_type] || '';
        var re = roleEmoji[c.role_type] || '🤖';
        var active = c.status === 'active';
        var trig = (c.trigger_keywords || []).slice(0,3).join(', ');
        return '<div class="card coworker-card">' +
          '<div class="coworker-name">' +
            '<span class="active-dot ' + (active ? 'on' : 'off') + '"></span>' +
            re + ' ' + esc(c.name) +
          '</div>' +
          '<span class="coworker-role ' + rc + '">' + esc(c.role_type) + '</span>' +
          '<div class="coworker-id">' + esc(c.coworker_id) + '</div>' +
          '<div class="coworker-desc">' + esc(c.description || '') + '</div>' +
          '<div class="coworker-meta">' +
            (c.schedule ? '<span class="coworker-meta-item">🕐 <span class="schedule-tag">' + esc(c.schedule) + '</span></span>' : '') +
            (trig ? '<span class="coworker-meta-item">🔑 ' + esc(trig) + '</span>' : '') +
            '<span style="margin-left:auto"><button class="btn btn-sm" onclick="triggerCoworker(\'' + esc(c.coworker_id) + '\')">▶ Run</button></span>' +
          '</div>' +
        '</div>';
      }).join('');
    })
    .catch(function(){});
}

function loadActivity() {
  fetch(API + '/activity')
    .then(function(r){ return r.json(); })
    .then(function(d){
      var feed = document.getElementById('activity-feed');
      if (!d.activity.length) {
        feed.innerHTML = '<div class="empty">No activity yet</div>';
        return;
      }
      feed.innerHTML = d.activity.map(function(a){
        var hasError = (a.results || []).some(function(r){ return r.status === 'error'; });
        var statusCls = hasError ? 'error' : 'success';
        var statusText = hasError ? '⚠ error' : '✓ ok';
        var ts = a.started_at ? new Date(a.started_at).toLocaleString() : 'unknown';
        var dur = a.duration_ms != null ? (a.duration_ms + 'ms') : '';
        return '<div class="activity-item">' +
          '<span class="activity-dot"></span>' +
          '<div class="activity-info">' +
            '<div class="activity-title">' + esc(a.run_name || a.coworker_id) + '</div>' +
            '<div class="activity-meta">' + esc(a.trigger_reason || '') + ' · ' + ts + (dur ? ' · ' + dur : '') + '</div>' +
          '</div>' +
          '<span class="activity-status ' + statusCls + '">' + statusText + '</span>' +
        '</div>';
      }).join('');
    })
    .catch(function(){});
}

function loadMemory() {
  fetch(API + '/memory')
    .then(function(r){ return r.json(); })
    .then(function(d){
      document.getElementById('memory-count').textContent = d.count + ' entries';
      var panel = document.getElementById('memory-panel');
      if (!d.entries.length) {
        panel.innerHTML = '<div class="empty">No shared memory yet</div>';
        return;
      }
      panel.innerHTML = d.entries.slice(-5).reverse().map(function(e){
        var isHuman = e.author.indexOf('human') !== -1;
        return '<div class="memory-item">' +
          '<div class="memory-header">' +
            '<span class="memory-author' + (isHuman ? ' human' : '') + '">' + esc(e.author) + '</span>' +
            '<span class="memory-time">' + esc(e.timestamp) + '</span>' +
          '</div>' +
          '<div class="memory-body">' + esc(e.body || '') + '</div>' +
        '</div>';
      }).join('');
    })
    .catch(function(){});
}

// ---- Actions ----
function quickRunMorningBrief() {
  fetch(API + '/coworkers/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({coworker_id: 'ops/morning-brief'})
  })
  .then(function(r){ return r.json(); })
  .then(function(d){
    if (d.success) {
      showToast('✅ Morning Brief dispatched! Run ID: ' + d.run_id, 'success');
      loadDashboard();
    } else {
      showToast('❌ ' + (d.error || 'Failed'), 'error');
    }
  })
  .catch(function(e){ showToast('❌ Network error', 'error'); });
}

function triggerCoworker(id) {
  fetch(API + '/coworkers/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({coworker_id: id})
  })
  .then(function(r){ return r.json(); })
  .then(function(d){
    if (d.success) {
      showToast('✅ ' + id + ' dispatched!', 'success');
      loadDashboard();
    } else {
      showToast('❌ ' + (d.error || 'Failed'), 'error');
    }
  })
  .catch(function(e){ showToast('❌ Network error', 'error'); });
}

function openAddMemory() { openModal('modal-memory'); }
function submitMemory() {
  var entry = document.getElementById('mem-entry').value.trim();
  var author = document.getElementById('mem-author').value.trim() || 'dashboard';
  if (!entry) { showToast('Please enter memory text', 'error'); return; }
  fetch(API + '/memory', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({entry: entry, author: author})
  })
  .then(function(r){ return r.json(); })
  .then(function(d){
    if (d.success) {
      showToast('✅ Memory added!', 'success');
      document.getElementById('mem-entry').value = '';
      closeModal('modal-memory');
      loadDashboard();
    } else {
      showToast('❌ ' + (d.error || 'Failed'), 'error');
    }
  })
  .catch(function(e){ showToast('❌ Network error', 'error'); });
}

function openViewRegistry() {
  fetch(API + '/registry/skills')
    .then(function(r){ return r.json(); })
    .then(function(d){
      var content = document.getElementById('registry-content');
      if (!d.skills.length) {
        content.innerHTML = '<div class="empty">No skills registered</div>';
        return;
      }
      content.innerHTML = d.skills.map(function(s){
        var ratingColor = 'var(--accent)';
        if (s.rating === 'B') ratingColor = 'var(--yellow)';
        if (s.rating === 'C') ratingColor = 'var(--text-muted)';
        return '<div class="memory-item" style="padding:8px 0;">' +
          '<div class="memory-header">' +
            '<span class="memory-author">' + esc(s.skill_id) + ' v' + esc(s.version) + '</span>' +
            '<span class="schedule-tag" style="color:' + ratingColor + '">' + esc(s.rating) + ' ' + esc(s.score||'') + '</span>' +
          '</div>' +
          '<div class="memory-body">' + esc(s.description || '') + '</div>' +
          '<div style="margin-top:4px;font-size:11px;color:var(--text-muted)">' +
            'Tags: ' + (s.tags||[]).join(', ') + ' · Status: ' + esc(s.status||'') +
          '</div>' +
        '</div>';
      }).join('');
      openModal('modal-registry');
    })
    .catch(function(){});
}

function loadKanbanStats() {
  fetch(API + '/kanban/stats')
    .then(function(r){ return r.json(); })
    .then(function(d){
      if (d.success) {
        document.getElementById('stat-kanban').textContent = d.total;
      }
    })
    .catch(function(){});
}

function loadKanban() {
  fetch(API + '/kanban/tasks')
    .then(function(r){ return r.json(); })
    .then(function(d){
      var board = document.getElementById('kanban-board');
      document.getElementById('kanban-count').textContent = d.total + ' tasks';
      if (!d.total) {
        board.innerHTML = '<div class="empty">No kanban tasks — create one via <code>kanban_create</code> or the Hermes CLI</div>';
        return;
      }
      var cols = d.columns;
      var colDefs = [
        {key: 'todo', label: '📥 To Do', cls: 'kanban-col-todo'},
        {key: 'ready', label: '✅ Ready', cls: 'kanban-col-ready'},
        {key: 'in_progress', label: '🔄 In Progress', cls: 'kanban-col-progress'},
        {key: 'blocked', label: '🚫 Blocked', cls: 'kanban-col-blocked'},
        {key: 'done', label: '✔️ Done', cls: 'kanban-col-done'},
      ];
      board.innerHTML = colDefs.map(function(cd){
        var tasks = cols[cd.key] || [];
        var cardsHtml = tasks.length
          ? tasks.map(function(t){
              var prioCls = t.priority <= 0 ? 'p0' : t.priority <= 1 ? 'p1' : 'p2';
              var age = t.createdAt ? Math.floor((Date.now() - t.createdAt*1000) / 3600000) + 'h ago' : '';
              return '<div class="kanban-card" onclick="openKanbanTask(\'' + esc(t.id) + '\')">' +
                '<div class="kanban-card-title">' + esc(t.title) + '</div>' +
                '<div class="kanban-card-meta">' +
                  '<span class="kanban-card-assignee">' + esc(t.assignee || 'unassigned') + '</span>' +
                  '<span class="kanban-card-priority ' + prioCls + '">P' + (t.priority||0) + '</span>' +
                '</div>' +
                (age ? '<div style="font-size:10px;color:var(--text-muted);margin-top:4px">' + age + '</div>' : '') +
              '</div>';
            }).join('')
          : '<div class="empty" style="padding:12px;font-size:11px">—</div>';
        return '<div class="kanban-column ' + cd.cls + '">' +
          '<div class="kanban-col-header">' + cd.label + '<span class="count">' + tasks.length + '</span></div>' +
          '<div class="kanban-cards">' + cardsHtml + '</div>' +
        '</div>';
      }).join('');
    })
    .catch(function(){});
}

function openKanbanTask(taskId) {
  fetch(API + '/kanban/tasks/' + taskId)
    .then(function(r){ return r.json(); })
    .then(function(d){
      if (!d.success) { showToast('Task not found', 'error'); return; }
      var t = d.task;
      var statusLabels = {
        todo: '📥 To Do', ready: '✅ Ready', in_progress: '🔄 In Progress',
        blocked: '🚫 Blocked', done: '✔️ Done', archived: '📦 Archived'
      };
      var created = t.createdAt ? new Date(t.createdAt*1000).toLocaleString() : '—';
      var html = '<h3>' + esc(t.title) + '</h3>' +
        '<div class="kanban-detail-row"><div class="kanban-detail-label">Status</div><div class="kanban-detail-value">' + (statusLabels[t.status] || t.status) + '</div></div>' +
        '<div class="kanban-detail-row"><div class="kanban-detail-label">Assignee</div><div class="kanban-detail-value">' + esc(t.assignee || 'unassigned') + ' <span class="kanban-card-priority p' + (t.priority<=0?'0':t.priority<=1?'1':'2') + '">P' + (t.priority||0) + '</span></div></div>' +
        '<div class="kanban-detail-row"><div class="kanban-detail-label">Created</div><div class="kanban-detail-value">' + created + '</div></div>' +
        '<div class="kanban-detail-row"><div class="kanban-detail-label">ID</div><div class="kanban-detail-value" style="font-family:monospace;font-size:11px">' + esc(t.id) + '</div></div>' +
        (t.body ? '<div class="kanban-detail-row"><div class="kanban-detail-label">Description</div><div class="kanban-detail-body">' + esc(t.body || '') + '</div></div>' : '') +
        (t.workspaceKind ? '<div class="kanban-detail-row"><div class="kanban-detail-label">Workspace</div><div class="kanban-detail-value">' + esc(t.workspaceKind) + (t.workspacePath ? ' → ' + esc(t.workspacePath) : '') + '</div></div>' : '');
      document.getElementById('kanban-detail-content').innerHTML = html;
      document.getElementById('kanban-drawer').classList.add('open');
    })
    .catch(function(){ showToast('Network error', 'error'); });
}

function closeKanbanDrawer() {
  document.getElementById('kanban-drawer').classList.remove('open');
}

function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ---- Init ----
loadDashboard();
// Auto-refresh every 30s
setInterval(loadDashboard, 30000);
</script>

</body>
</html>"""


@app.route("/")
def dashboard():
    """Serve the single-page web dashboard."""
    return render_template_string(DASHBOARD_HTML)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("⚡ Hermes Dashboard starting...")
    print(f"   Project root: {PROJECT_ROOT}")
    print(f"   Dashbord URL: http://localhost:5002")
    print(f"   API Base:     http://localhost:5002/api")
    print()
    app.run(host="0.0.0.0", port=5002, debug=False)
