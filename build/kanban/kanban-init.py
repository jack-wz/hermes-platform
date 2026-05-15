#!/usr/bin/env python3
"""
kanban-init.py — Initialize the Hermes Kanban database with schema and seed data.

Usage:
    python build/kanban/kanban-init.py           # create schema + seed
    python build/kanban/kanban-init.py --schema-only   # schema only
    python build/kanban/kanban-init.py --seed-only     # seed only (schema must exist)
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path.home() / ".hermes" / "kanban.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    description     TEXT DEFAULT '',
    assignee        TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'todo'
                    CHECK(status IN ('todo','ready','in_progress','blocked','done','archived')),
    priority        INTEGER NOT NULL DEFAULT 2
                    CHECK(priority BETWEEN 0 AND 3),
    board           TEXT NOT NULL DEFAULT 'execution',
    workspace_kind  TEXT DEFAULT '',
    workspace_path  TEXT DEFAULT '',
    created_by      TEXT DEFAULT 'system',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    started_at      TEXT,
    completed_at    TEXT,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    claim_lock      TEXT,
    claim_expires   TEXT,
    idempotency_key TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    worker_pid      INTEGER,
    last_failure_error TEXT,
    max_runtime_seconds INTEGER,
    last_heartbeat_at TEXT,
    current_run_id  TEXT,
    workflow_template_id TEXT,
    current_step_key TEXT,
    max_retries     INTEGER DEFAULT 3
);

CREATE TABLE IF NOT EXISTS task_comments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    author      TEXT NOT NULL DEFAULT 'system',
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS task_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    event_type  TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    created_by  TEXT DEFAULT 'system',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee);
CREATE INDEX IF NOT EXISTS idx_tasks_board ON tasks(board);
CREATE INDEX IF NOT EXISTS idx_comments_task ON task_comments(task_id);
CREATE INDEX IF NOT EXISTS idx_events_task ON task_events(task_id);
"""

SEED_TASKS = [
    {
        "id": "t-memv2-phased",
        "title": "Memory v2 Phase D — npm接入评估 (@tencentdb-agent-memory)",
        "description": "评估 @tencentdb-agent-memory npm 包直接接入 vs 继续自维护。对比自主实现 vs npm 包的成本/收益。产出一页决策表。",
        "assignee": "team_skillops",
        "status": "todo",
        "priority": 1,
        "board": "execution",
        "workspace_kind": "evaluation",
    },
    {
        "id": "t-content-cms",
        "title": "Phase 7 — Content Publishing CMS",
        "description": "实现内容发布管线管理界面。当前 content pipeline 有 24h 自动发布治理规则但无管理 UI。",
        "assignee": "team_content",
        "status": "todo",
        "priority": 2,
        "board": "execution",
        "workspace_kind": "feature",
    },
    {
        "id": "t-cronalytics-followup",
        "title": "Cronalytics 外联跟进 — lanes-contact Issue #5",
        "description": "GitHub Issue lanes-sh/app#5 待对方回复。需定期检查状态，超时后重试。",
        "assignee": "team_growth",
        "status": "todo",
        "priority": 2,
        "board": "execution",
        "workspace_kind": "outreach",
    },
    {
        "id": "t-org-review-weekly",
        "title": "周五组织回顾 — Cron 自动化验证",
        "description": "验证 friday-resource-org-review cron job 产出质量。检查最近 7 天 cron/jobs、reviews、verification、skills 状态。",
        "assignee": "team_skillops",
        "status": "todo",
        "priority": 1,
        "board": "execution",
        "workspace_kind": "ops",
    },
    {
        "id": "t-kanban-schema",
        "title": "Kanban DB schema + seed + write endpoints",
        "description": "创建 kanban.db schema（tasks/comments/events 表），初始化种子数据，为 Dashboard 添加 POST/PATCH 写端点。",
        "assignee": "team_build",
        "status": "in_progress",
        "priority": 0,
        "board": "execution",
        "workspace_kind": "feature",
    },
    {
        "id": "t-memory-v2-symbolic-cron",
        "title": "SymbolicMemory 定时压缩 — Cron 集成",
        "description": "将 Phase C SymbolicMemory 压缩接入 cron：每日自动压缩 L0→Mermaid graph，产出压缩报告。",
        "assignee": "team_build",
        "status": "todo",
        "priority": 2,
        "board": "execution",
        "workspace_kind": "feature",
    },
    {
        "id": "t-governance-audit",
        "title": "治理规则完整性审计 — CONTEXT.md + ADR + 对齐 + 交接",
        "description": "验证新治理规则是否被所有 agent 正确加载和执行。检查 CONTEXT.md 术语覆盖率、ADR 引用完整性、对齐/交接协议合规性。",
        "assignee": "team_skillops",
        "status": "todo",
        "priority": 1,
        "board": "execution",
        "workspace_kind": "audit",
    },
    {
        "id": "t-marketplace-phase5",
        "title": "Marketplace Phase 5 — SKILL.md Registry + Plugin Bridge 完善",
        "description": "完善 Registry 搜索/过滤/发布管线。Plugin Bridge 已有基础骨架，需补全双向同步和 skill 依赖解析。",
        "assignee": "team_build",
        "status": "ready",
        "priority": 1,
        "board": "execution",
        "workspace_kind": "feature",
    },
    {
        "id": "t-signal-daily-scan",
        "title": "Discovery 信号扫描 — 每日自动化",
        "description": "team_signal 每日自动扫描 GitHub trending、HN、X 等源，产出信号摘要。当前手动触发，需 cron 化。",
        "assignee": "team_signal",
        "status": "ready",
        "priority": 1,
        "board": "discovery",
        "workspace_kind": "ops",
    },
    {
        "id": "t-prediction-council-weekly",
        "title": "Prediction Council 周度战略辩论 — 自动简报",
        "description": "board_prediction 每周自动产出战略辩论简报。当前 cron 已配置，需验证产出质量并优化输入信号管线。",
        "assignee": "team_council",
        "status": "ready",
        "priority": 2,
        "board": "prediction",
        "workspace_kind": "ops",
    },
]


def init_db(db_path: Path, seed: bool = True, schema_only: bool = False) -> None:
    """Initialize the Kanban database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Schema
    conn.executescript(SCHEMA_SQL)
    print(f"✓ Schema created ({db_path})")

    if schema_only:
        conn.close()
        return

    # Seed
    if seed:
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.cursor()
        for task in SEED_TASKS:
            cur.execute(
                """INSERT OR IGNORE INTO tasks
                   (id, title, description, assignee, status, priority, board,
                    workspace_kind, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task["id"], task["title"], task["description"],
                 task["assignee"], task["status"], task["priority"],
                 task["board"], task["workspace_kind"], now, now),
            )
            # Add a creation event
            cur.execute(
                """INSERT INTO task_events (task_id, event_type, new_value, created_at)
                   VALUES (?, 'created', ?, ?)""",
                (task["id"], task["status"], now),
            )
        conn.commit()
        print(f"✓ Seeded {len(SEED_TASKS)} tasks with creation events")

    # Stats
    cur = conn.cursor()
    cur.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
    stats = {row[0]: row[1] for row in cur.fetchall()}
    total = sum(stats.values())
    print(f"  Total: {total} tasks")
    for status in ["todo", "ready", "in_progress", "blocked", "done"]:
        count = stats.get(status, 0)
        icon = {"todo": "⬜", "ready": "🟡", "in_progress": "🔵", "blocked": "🔴", "done": "✅"}.get(status, "❓")
        print(f"  {icon} {status}: {count}")

    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize Hermes Kanban database")
    parser.add_argument("--db", default=str(DEFAULT_DB), help=f"Database path (default: {DEFAULT_DB})")
    parser.add_argument("--schema-only", action="store_true", help="Create schema only, no seed data")
    parser.add_argument("--seed-only", action="store_true", help="Seed only (schema must exist)")
    args = parser.parse_args()

    db_path = Path(args.db)

    if args.seed_only:
        if not db_path.exists():
            print(f"✗ Database not found at {db_path}. Run without --seed-only first.", file=sys.stderr)
            sys.exit(1)
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys=ON")
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.cursor()
        for task in SEED_TASKS:
            cur.execute(
                """INSERT OR IGNORE INTO tasks
                   (id, title, description, assignee, status, priority, board,
                    workspace_kind, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task["id"], task["title"], task["description"],
                 task["assignee"], task["status"], task["priority"],
                 task["board"], task["workspace_kind"], now, now),
            )
        conn.commit()
        conn.close()
        print(f"✓ Seeded {len(SEED_TASKS)} tasks")
    else:
        init_db(db_path, seed=not args.schema_only, schema_only=args.schema_only)


if __name__ == "__main__":
    main()
