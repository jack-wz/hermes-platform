#!/usr/bin/env python3
"""
hermes-coworker — AI Coworker Engine CLI + importable module.

Manages AI coworkers (named agents with role definitions, bound skills,
schedules, and keyword triggers).  Every skill execution is wrapped through
hermes-audit so that an auditable receipt is produced.

Usage:
    hermes-coworker.py register <coworker_file>   # register a coworker
    hermes-coworker.py list                        # list all coworkers
    hermes-coworker.py run <coworker_id>           # execute now
    hermes-coworker.py schedule                    # show upcoming executions
    hermes-coworker.py trigger <keyword>           # trigger by keyword

Python API:
    from hermes_coworker import CoworkerEngine
    engine = CoworkerEngine()
    engine.register("ops/morning-brief.COWORKER.md")
    engine.list_coworkers()
    engine.run("ops/morning-brief")
    engine.schedule_upcoming()
    engine.trigger("晨报")

Dependencies: Python 3.8+, PyYAML (pip install pyyaml)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Paths — resolved relative to this script (build/workspace/)
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent  # -> ~/.hermes/workspace
REGISTRY_PATH = PROJECT_ROOT / "registry" / "coworkers.json"
SKILLS_REGISTRY_PATH = PROJECT_ROOT / "registry" / "skills.json"
COWORKERS_DIR = PROJECT_ROOT / "registry" / "coworkers"
AUDIT_SCRIPT = PROJECT_ROOT / "build" / "phase3" / "hermes-audit.py"
LOGS_DIR = PROJECT_ROOT / "logs" / "coworkers"

# ---------------------------------------------------------------------------
# YAML helper (lazy import to give clean errors)
# ---------------------------------------------------------------------------
def _load_yaml():
    try:
        import yaml
        return yaml
    except ImportError:
        print(
            "ERROR: PyYAML is required. Install it with:  pip install pyyaml",
            file=sys.stderr,
        )
        sys.exit(2)


# ---------------------------------------------------------------------------
# Cron parser (5-field cron: minute hour dom month dow)
# ---------------------------------------------------------------------------
_CRON_FIELD_RANGES = [
    (0, 59),   # minute
    (0, 23),   # hour
    (1, 31),   # day of month
    (1, 12),   # month
    (0, 6),    # day of week (0=Sunday)
]
_MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def _parse_cron_field(field: str, lo: int, hi: int) -> set[int]:
    """Parse a single cron field into a set of valid values."""
    if field == "*":
        return set(range(lo, hi + 1))
    values: set[int] = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, step_str = part.split("/", 1)
            step = int(step_str)
        if part == "*":
            low, high = lo, hi
        elif "-" in part:
            a, b = part.split("-", 1)
            low, high = int(a), int(b)
        else:
            low = high = int(part)
        for v in range(low, high + 1, step):
            if lo <= v <= hi:
                values.add(v)
    return values


def cron_next(expression: str, from_dt: Optional[datetime] = None, limit: int = 5) -> list[datetime]:
    """Return the next *limit* UTC datetimes matching a 5-field cron expression."""
    if from_dt is None:
        from_dt = datetime.now(timezone.utc)
    else:
        from_dt = from_dt.astimezone(timezone.utc)

    fields = expression.strip().split()
    if len(fields) != 5:
        return []

    sets = [_parse_cron_field(f, lo, hi) for f, (lo, hi) in zip(fields, _CRON_FIELD_RANGES)]
    mins, hrs, doms, mons, dows = sets

    results: list[datetime] = []
    # Start from the next minute to avoid the current partial minute
    candidate = from_dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
    failsafe = 0

    while len(results) < limit and failsafe < 525600:  # max 1 year of minutes
        if candidate.month in mons:
            day_matches = candidate.day in doms
            dow_matches = candidate.weekday() in dows
            # Standard cron: dom OR dow (if both are not '*')
            dom_specified = fields[2] != "*"
            dow_specified = fields[4] != "*"
            if dom_specified and dow_specified:
                day_ok = day_matches or dow_matches
            elif dom_specified:
                day_ok = day_matches
            elif dow_specified:
                day_ok = dow_matches
            else:
                day_ok = True
            if day_ok and candidate.hour in hrs and candidate.minute in mins:
                results.append(candidate)
        candidate += timedelta(minutes=1)
        failsafe += 1

    return results


# ---------------------------------------------------------------------------
# Frontmatter parser (mirrors hermes-audit.py logic)
# ---------------------------------------------------------------------------
def parse_frontmatter(filepath: str) -> dict:
    """Parse YAML frontmatter from a .COWORKER.md or .SKILL.md file.

    Returns dict with keys: 'ok' (bool), 'fm' (dict|None), 'body' (str|None), 'error' (str|None).
    """
    result: dict = {"ok": False, "fm": None, "body": None, "error": None}
    try:
        content = Path(filepath).read_text(encoding="utf-8")
    except FileNotFoundError:
        result["error"] = f"File not found: {filepath}"
        return result
    except Exception as exc:
        result["error"] = f"Cannot read file: {exc}"
        return result

    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        result["error"] = "No YAML frontmatter found (file must start with ---)"
        return result

    end_idx: Optional[int] = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        result["error"] = "Unclosed frontmatter: missing closing ---"
        return result

    frontmatter_text = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1:])

    yaml = _load_yaml()
    try:
        fm = yaml.safe_load(frontmatter_text)
    except Exception as exc:
        result["error"] = f"YAML parse error: {exc}"
        return result

    if fm is None:
        result["error"] = "Empty frontmatter (no key-value pairs)"
        return result
    if not isinstance(fm, dict):
        result["error"] = "Frontmatter is not a YAML mapping"
        return result

    result["ok"] = True
    result["fm"] = fm
    result["body"] = body
    return result


# ---------------------------------------------------------------------------
# Registry I/O
# ---------------------------------------------------------------------------
def load_registry() -> dict:
    """Load the coworker registry JSON file."""
    if not REGISTRY_PATH.exists():
        return {
            "registry_version": "1.0.0",
            "updated_at": "",
            "coworkers": [],
        }
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_registry(data: dict) -> None:
    """Persist the coworker registry and bump the timestamp."""
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# CoworkerEngine — the importable Python API
# ---------------------------------------------------------------------------
class CoworkerEngine:
    """AI Coworker engine — register, list, run, schedule, trigger."""

    def __init__(self, project_root: Optional[Path] = None):
        if project_root:
            self.project_root = project_root
        else:
            self.project_root = PROJECT_ROOT

        self.registry_path = self.project_root / "registry" / "coworkers.json"
        self.skills_registry_path = self.project_root / "registry" / "skills.json"
        self.coworkers_dir = self.project_root / "registry" / "coworkers"
        self.audit_script = self.project_root / "build" / "phase3" / "hermes-audit.py"
        self.logs_dir = self.project_root / "logs" / "coworkers"

    # ---- registration ----
    def register(self, coworker_file: str) -> dict:
        """Parse a .COWORKER.md file, validate skills, and add to registry."""
        target = Path(coworker_file)
        if not target.is_absolute():
            target = Path.cwd() / target
        target = target.resolve()

        parsed = parse_frontmatter(str(target))
        if not parsed["ok"]:
            return {"success": False, "error": parsed["error"]}

        fm: dict = parsed["fm"]

        # Required fields
        coworker_id = fm.get("coworker_id", "")
        if not coworker_id:
            return {"success": False, "error": "Missing required field: coworker_id"}

        name = fm.get("name", coworker_id)
        name_en = fm.get("name_en", name)
        version = fm.get("version", "0.0.0")
        author = fm.get("author", "unknown")
        description = fm.get("description", "")[:200]
        role_type = fm.get("role_type", "general")
        schedule = fm.get("schedule", "")
        skills = fm.get("skills", [])
        permissions = fm.get("permissions", {})
        memory = fm.get("memory", {"shared": False, "scope": "private"})
        trigger_keywords = fm.get("trigger_keywords", [])

        # Validate skills exist in registry
        valid_skills = []
        invalid_skills = []
        for skill_id in skills:
            if self._skill_exists(skill_id):
                valid_skills.append(skill_id)
            else:
                invalid_skills.append(skill_id)

        if invalid_skills:
            return {
                "success": False,
                "error": f"Skills not found in registry: {', '.join(invalid_skills)}",
            }

        # Validate schedule
        if schedule and not self._validate_cron(schedule):
            return {"success": False, "error": f"Invalid cron schedule: {schedule}"}

        # Build registry entry
        entry = {
            "coworker_id": coworker_id,
            "name": name,
            "name_en": name_en,
            "version": version,
            "author": author,
            "description": description,
            "role_type": role_type,
            "schedule": schedule,
            "skills": valid_skills,
            "permissions": permissions,
            "memory": memory,
            "trigger_keywords": trigger_keywords,
            "path": str(target.relative_to(self.project_root)),
            "status": "active",
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }

        reg = self._load_registry()
        # Upsert
        existing_idx = None
        for i, c in enumerate(reg["coworkers"]):
            if c["coworker_id"] == coworker_id:
                existing_idx = i
                break

        if existing_idx is not None:
            reg["coworkers"][existing_idx] = entry
            action = "updated"
        else:
            reg["coworkers"].append(entry)
            action = "registered"

        self._save_registry_data(reg)
        return {"success": True, "action": action, "coworker_id": coworker_id}

    # ---- list ----
    def list_coworkers(self) -> list[dict]:
        """Return the list of all registered coworkers."""
        return self._load_registry().get("coworkers", [])

    # ---- run ----
    def run(self, coworker_id: str, trigger_reason: Optional[str] = None) -> dict:
        """Execute a coworker: run each bound skill through hermes-audit."""
        coworker = self._find_coworker(coworker_id)
        if not coworker:
            return {"success": False, "error": f"Coworker not found: {coworker_id}"}

        run_id = str(uuid.uuid4())[:8]
        started_at = datetime.now(timezone.utc).isoformat()
        start_ts = time.monotonic()

        results = []
        receipts = []

        for skill_id in coworker.get("skills", []):
            skill_path = self._resolve_skill_path(skill_id)
            if not skill_path:
                results.append({
                    "skill_id": skill_id,
                    "status": "error",
                    "error": "Skill file not found",
                })
                continue

            # Default command: echo the skill execution (placeholder)
            cmd = f"echo '[hermes-coworker] Executing {skill_id} for {coworker_id}'"
            receipt = self._run_audit(str(skill_path), cmd)
            if receipt:
                receipts.append(receipt)
                results.append({
                    "skill_id": skill_id,
                    "status": receipt.get("execution", {}).get("status", "unknown"),
                    "receipt_id": receipt.get("receipt_id"),
                })
            else:
                results.append({
                    "skill_id": skill_id,
                    "status": "error",
                    "error": "Audit execution failed",
                })

        end_ts = time.monotonic()
        completed_at = datetime.now(timezone.utc).isoformat()
        duration_ms = int((end_ts - start_ts) * 1000)

        # Build run log entry
        run_log = {
            "run_id": run_id,
            "coworker_id": coworker_id,
            "run_name": coworker.get("name", coworker_id),
            "trigger_reason": trigger_reason or "manual",
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_ms": duration_ms,
            "results": results,
        }

        self._write_run_log(coworker_id, run_id, run_log, receipts)

        return {"success": True, "run_id": run_id, "run_log": run_log, "receipts": receipts}

    # ---- schedule ----
    def schedule_upcoming(self, limit: int = 10) -> list[dict]:
        """Return upcoming scheduled executions for all active coworkers."""
        coworkers = self.list_coworkers()
        now = datetime.now(timezone.utc)
        upcoming = []

        for c in coworkers:
            schedule = c.get("schedule", "")
            if not schedule or c.get("status") != "active":
                continue
            next_times = cron_next(schedule, from_dt=now, limit=limit)
            for nt in next_times:
                upcoming.append({
                    "coworker_id": c["coworker_id"],
                    "name": c.get("name", c["coworker_id"]),
                    "schedule": schedule,
                    "next_at": nt.isoformat(),
                })

        # Sort by next_at and crop
        upcoming.sort(key=lambda x: x["next_at"])
        return upcoming[:limit]

    # ---- trigger ----
    def trigger(self, keyword: str) -> dict:
        """Trigger all coworkers whose trigger_keywords match *keyword*."""
        coworkers = self.list_coworkers()
        keyword_lower = keyword.lower()
        matched = []

        for c in coworkers:
            if c.get("status") != "active":
                continue
            keywords = [k.lower() for k in c.get("trigger_keywords", [])]
            if any(keyword_lower in kw or kw in keyword_lower for kw in keywords):
                matched.append(c)

        if not matched:
            return {"success": False, "error": f"No coworkers match keyword: {keyword}"}

        results = []
        for c in matched:
            result = self.run(c["coworker_id"], trigger_reason=f"keyword:{keyword}")
            results.append(result)

        return {"success": True, "matched": len(matched), "results": results}

    # === internal helpers ===

    def _load_registry(self) -> dict:
        if not self.registry_path.exists():
            return {"registry_version": "1.0.0", "updated_at": "", "coworkers": []}
        with open(self.registry_path, encoding="utf-8") as f:
            return json.load(f)

    def _save_registry_data(self, data: dict) -> None:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _find_coworker(self, coworker_id: str) -> Optional[dict]:
        reg = self._load_registry()
        for c in reg.get("coworkers", []):
            if c["coworker_id"] == coworker_id:
                return c
        return None

    def _skill_exists(self, skill_id: str) -> bool:
        """Check if skill_id exists in the skills registry."""
        if not self.skills_registry_path.exists():
            return False
        with open(self.skills_registry_path, encoding="utf-8") as f:
            reg = json.load(f)
        return any(s["skill_id"] == skill_id for s in reg.get("skills", []))

    def _resolve_skill_path(self, skill_id: str) -> Optional[Path]:
        """Resolve a skill_id to its absolute file path via the skills registry."""
        if not self.skills_registry_path.exists():
            return None
        with open(self.skills_registry_path, encoding="utf-8") as f:
            reg = json.load(f)
        for s in reg.get("skills", []):
            if s["skill_id"] == skill_id:
                return self.project_root / s["path"]
        return None

    def _run_audit(self, skill_path: str, cmd: str) -> Optional[dict]:
        """Execute hermes-audit.py for a skill and return the receipt."""
        if not self.audit_script.exists():
            # fallback: try absolute path
            if not AUDIT_SCRIPT.exists():
                return None

        audit_script = str(self.audit_script) if self.audit_script.exists() else str(AUDIT_SCRIPT)
        try:
            proc = subprocess.run(
                [sys.executable, audit_script, "--skill", skill_path, "--cmd", cmd],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if proc.returncode not in (0, 1):  # audit may exit 1 on cmd failure
                return None
            return json.loads(proc.stdout.strip().split("\n")[-1])  # last line has receipt
        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
            return None

    def _write_run_log(self, coworker_id: str, run_id: str, run_log: dict, receipts: list[dict]) -> None:
        """Persist the execution log and receipts."""
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = self.logs_dir / f"{coworker_id.replace('/', '_')}_{run_id}.json"
        full_log = {
            **run_log,
            "receipts": receipts,
        }
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(full_log, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _validate_cron(expression: str) -> bool:
        """Check if a 5-field cron expression is syntactically valid."""
        fields = expression.strip().split()
        if len(fields) != 5:
            return False
        try:
            for f, (lo, hi) in zip(fields, _CRON_FIELD_RANGES):
                _parse_cron_field(f, lo, hi)
            return True
        except (ValueError, IndexError):
            return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _fmt_duration(ms: int) -> str:
    if ms < 1000:
        return f"{ms}ms"
    elif ms < 60000:
        return f"{ms / 1000:.1f}s"
    else:
        return f"{ms / 60000:.1f}m"


def cmd_register(engine: CoworkerEngine, filepath: str) -> None:
    result = engine.register(filepath)
    if result["success"]:
        print(f"✓ {result['action']}: {result['coworker_id']}")
    else:
        print(f"✗ Error: {result['error']}", file=sys.stderr)
        sys.exit(1)


def cmd_list(engine: CoworkerEngine) -> None:
    coworkers = engine.list_coworkers()
    if not coworkers:
        print("(no coworkers registered)")
        return

    print(f"Coworker Registry ({len(coworkers)} coworkers):\n")
    print(f"  {'ID':<30s} {'NAME':<12s} {'TYPE':<12s} {'SCHEDULE':<12s} {'STATUS':<8s} SKILLS")
    print(f"  {'─' * 30} {'─' * 12} {'─' * 12} {'─' * 12} {'─' * 8} {'─' * 20}")
    for c in coworkers:
        schedule = c.get("schedule", "—")
        skills = ", ".join(c.get("skills", [])) or "—"
        print(
            f"  {c['coworker_id']:<30s} "
            f"{c.get('name', '')[:10]:<12s} "
            f"{c.get('role_type', '—')[:10]:<12s} "
            f"{schedule[:10]:<12s} "
            f"{c.get('status', '—')[:6]:<8s} "
            f"{skills[:30]}"
        )


def cmd_run(engine: CoworkerEngine, coworker_id: str) -> None:
    print(f"🚀 Running coworker: {coworker_id}")
    print(f"   Start: {datetime.now(timezone.utc).isoformat()}")
    print()

    result = engine.run(coworker_id)
    if not result["success"]:
        print(f"✗ Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    run_log = result["run_log"]
    print(f"   Run ID: {run_log['run_id']}")
    print(f"   Duration: {_fmt_duration(run_log['duration_ms'])}")
    print(f"   Skills executed: {len(run_log['results'])}")
    print()

    for r in run_log["results"]:
        status_icon = "✓" if r["status"] == "success" else "✗" if r["status"] in ("failure", "error") else "?"
        print(f"   {status_icon} {r['skill_id']}: {r['status']}")
        if r.get("receipt_id"):
            print(f"     receipt: {r['receipt_id']}")
    print(f"\n   Receipts: {len(result['receipts'])} generated")


def cmd_schedule(engine: CoworkerEngine) -> None:
    upcoming = engine.schedule_upcoming()
    if not upcoming:
        print("No upcoming scheduled executions.")
        return

    print(f"Upcoming scheduled executions ({len(upcoming)}):\n")
    print(f"  {'WHEN':<22s} {'COWORKER':<30s} {'SCHEDULE':<14s}")
    print(f"  {'─' * 22} {'─' * 30} {'─' * 14}")
    for u in upcoming:
        print(f"  {u['next_at']:<22s} {u['coworker_id']:<30s} {u['schedule']:<14s}")


def cmd_trigger(engine: CoworkerEngine, keyword: str) -> None:
    print(f"🔍 Triggering coworkers with keyword: \"{keyword}\"")
    result = engine.trigger(keyword)

    if not result["success"]:
        print(f"✗ {result['error']}", file=sys.stderr)
        sys.exit(1)

    print(f"   Matched: {result['matched']} coworker(s)")
    for r in result["results"]:
        if r["success"]:
            run_log = r["run_log"]
            print(f"   → {run_log['coworker_id']}: run_id={run_log['run_id']} "
                  f"({len(run_log['results'])} skills, {_fmt_duration(run_log['duration_ms'])})")
        else:
            print(f"   → Error: {r['error']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hermes AI Coworker Engine — manage and run AI coworkers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  hermes-coworker.py register ops/morning-brief.COWORKER.md
  hermes-coworker.py list
  hermes-coworker.py run ops/morning-brief
  hermes-coworker.py schedule
  hermes-coworker.py trigger 晨报
""",
    )
    sub = parser.add_subparsers(dest="command", help="Command")

    # register
    p_reg = sub.add_parser("register", help="Register a coworker from .COWORKER.md file")
    p_reg.add_argument("file", help="Path to .COWORKER.md file")

    # list
    sub.add_parser("list", help="List all registered coworkers")

    # run
    p_run = sub.add_parser("run", help="Execute a coworker now")
    p_run.add_argument("coworker_id", help="Coworker ID (e.g. ops/morning-brief)")

    # schedule
    sub.add_parser("schedule", help="Show upcoming scheduled executions")

    # trigger
    p_trig = sub.add_parser("trigger", help="Trigger coworkers by keyword")
    p_trig.add_argument("keyword", help="Trigger keyword")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    engine = CoworkerEngine()

    if args.command == "register":
        cmd_register(engine, args.file)
    elif args.command == "list":
        cmd_list(engine)
    elif args.command == "run":
        cmd_run(engine, args.coworker_id)
    elif args.command == "schedule":
        cmd_schedule(engine)
    elif args.command == "trigger":
        cmd_trigger(engine, args.keyword)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
