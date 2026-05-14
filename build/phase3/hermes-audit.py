#!/usr/bin/env python3
"""
hermes-audit — CLI wrapper that captures skill execution metadata into a
structured, verifiable audit receipt (JSON).

Usage:
    hermes-audit.py --skill <path/to/SKILL.md> --cmd <command> [--output <path>]
    hermes-audit.py --skill <path/to/SKILL.md> --cmd <command> --pretty

Integration:
    Scans the skill file with hermes-scan (Phase 2) to obtain rating/score,
    then wraps the external command and records timestamps, exit code, and a
    reproducible SHA-256 input hash.  Token/cost estimates come from the
    skill's declared cost block because real API-level token counts cannot be
    captured from an arbitrary external command.

Receipt format (audit receipt v1.0):
    {
      "receipt_id": "<uuid4>",
      "timestamp": "<ISO8601>",
      "skill": {
        "skill_id": "...",
        "version": "...",
        "rating": "A-F",
        "score": 0-100,
        "declared_cost": {...}
      },
      "execution": {
        "command": "<shell command>",
        "started_at": "<ISO8601>",
        "completed_at": "<ISO8601>",
        "duration_ms": 1234,
        "exit_code": 0,
        "status": "success|failure|error"
      },
      "audit": {
        "input_hash": "sha256...",
        "output_summary": "<first N chars of stdout+stderr>",
        "token_cost": {
          "estimated_prompt_tokens": 2000,
          "estimated_completion_tokens": 1000,
          "estimated_total_tokens": 3000,
          "estimated_cost_usd": 0.006
        }
      },
      "signature": "sha256 of canonical JSON of the receipt (minus signature field)"
    }

Dependencies:  Python 3.8+, PyYAML (pip install pyyaml)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_yaml():
    """Lazy-import PyYAML so we can give a clean error if it is missing."""
    try:
        import yaml
        return yaml
    except ImportError:
        print(
            "ERROR: PyYAML is required. Install it with:  pip install pyyaml",
            file=sys.stderr,
        )
        sys.exit(2)


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with 'Z' suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_hex(data: str | bytes) -> str:
    """Return the SHA-256 hex digest of *data*."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Any) -> str:
    """Serialize *obj* to a canonical (sorted-key) JSON string with no trailing
    whitespace — used so that the receipt signature is deterministic."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# SKILL.md frontmatter parsing (mirrors hermes-scan.py logic)
# ---------------------------------------------------------------------------

def parse_skill_frontmatter(filepath: str) -> dict:
    """Parse YAML frontmatter from a SKILL.md file.

    Returns a dict with keys: 'ok' (bool), 'fm' (dict|None),
    'body' (str|None), 'error' (str|None).
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
# hermes-scan integration
# ---------------------------------------------------------------------------

def scan_skill(skill_path: str) -> dict:
    """Run hermes-scan.py against *skill_path* and return the JSON report.

    hermes-scan.py is expected to be in the same directory as this script.
    """
    script_dir = Path(__file__).resolve().parent
    scan_script = script_dir / "hermes-scan.py"

    if not scan_script.exists():
        # Fallback: look in the build/phase2 directory
        scan_script = script_dir.parent / "phase2" / "hermes-scan.py"

    if not scan_script.exists():
        return {
            "skill_id": None,
            "rating": "F",
            "score": 0,
            "error": "hermes-scan.py not found — cannot rate skill",
        }

    try:
        proc = subprocess.run(
            [sys.executable, str(scan_script), str(skill_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            return {
                "skill_id": None,
                "rating": "F",
                "score": 0,
                "error": f"hermes-scan exited with code {proc.returncode}: {proc.stderr.strip()[:200]}",
            }
        return json.loads(proc.stdout)
    except subprocess.TimeoutExpired:
        return {
            "skill_id": None,
            "rating": "F",
            "score": 0,
            "error": "hermes-scan timed out",
        }
    except json.JSONDecodeError:
        return {
            "skill_id": None,
            "rating": "F",
            "score": 0,
            "error": f"hermes-scan produced invalid JSON: {proc.stdout[:200] if proc else ''}",
        }
    except Exception as exc:
        return {
            "skill_id": None,
            "rating": "F",
            "score": 0,
            "error": f"hermes-scan failed: {exc}",
        }


# ---------------------------------------------------------------------------
# Token / cost estimation
# ---------------------------------------------------------------------------

# Blended rate: ~$2.00 / 1M tokens ($0.002 / 1K)
# This is a rough blend of prompt ($0.15-$3.00/1M) and completion ($0.60-$15.00/1M)
# across common models.  The receipt clearly labels these as *estimated*.
_ESTIMATED_COST_PER_1K_TOKENS = 0.002  # USD


def estimate_token_cost(fm: dict) -> dict:
    """Extract token estimates from the skill's cost block and compute USD cost.

    Returns a dict with keys matching the receipt's token_cost sub-object.
    """
    cost_block = fm.get("cost", {}) if isinstance(fm, dict) else {}
    if not isinstance(cost_block, dict):
        cost_block = {}

    te = cost_block.get("token_estimate", {})
    if not isinstance(te, dict):
        te = {}

    per_run = te.get("per_run", {})
    if not isinstance(per_run, dict):
        per_run = {}

    prompt = per_run.get("input", 0)
    completion = per_run.get("output", 0)
    total = per_run.get("total", prompt + completion)

    # Ensure numeric
    try:
        prompt = int(prompt)
    except (ValueError, TypeError):
        prompt = 0
    try:
        completion = int(completion)
    except (ValueError, TypeError):
        completion = 0
    try:
        total = int(total)
    except (ValueError, TypeError):
        total = prompt + completion

    # If the skill declared zero tokens but has a base cost, use the base
    if total == 0:
        base = te.get("base", 0)
        try:
            base = int(base)
        except (ValueError, TypeError):
            base = 0
        total = base
        prompt = base

    cost_usd = round((total * _ESTIMATED_COST_PER_1K_TOKENS) / 1000, 6)

    return {
        "estimated_prompt_tokens": prompt,
        "estimated_completion_tokens": completion,
        "estimated_total_tokens": total,
        "estimated_cost_usd": cost_usd,
    }


# ---------------------------------------------------------------------------
# Receipt builder
# ---------------------------------------------------------------------------

def build_receipt(
    skill_fm: dict,
    scan_report: dict,
    command: str,
    started_at: str,
    completed_at: str,
    duration_ms: int,
    exit_code: int,
    status: str,
    stdout_text: str,
    stderr_text: str,
) -> dict:
    """Assemble the audit receipt as a dict (unsigned)."""

    # --- Input hash (command + skill path for reproducibility) ---
    input_payload = f"skill:{scan_report.get('skill_id','')}|cmd:{command}"
    input_hash = sha256_hex(input_payload)

    # --- Output summary: first 500 chars of stdout, truncated ---
    combined_output = (stdout_text + "\n" + stderr_text).strip()
    if len(combined_output) > 500:
        output_summary = combined_output[:497] + "..."
    else:
        output_summary = combined_output

    receipt = {
        "receipt_id": str(uuid.uuid4()),
        "timestamp": utc_now_iso(),
        "skill": {
            "skill_id": scan_report.get("skill_id")
                       or skill_fm.get("skill_id"),
            "version": str(skill_fm.get("version", "unknown")),
            "rating": scan_report.get("rating", "F"),
            "score": scan_report.get("score", 0),
            "declared_cost": skill_fm.get("cost", {}) if isinstance(skill_fm, dict) else {},
        },
        "execution": {
            "command": command,
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_ms": duration_ms,
            "exit_code": exit_code,
            "status": status,
        },
        "audit": {
            "input_hash": input_hash,
            "output_summary": output_summary,
            "token_cost": estimate_token_cost(skill_fm),
        },
    }

    # Sign: SHA-256 of the canonical JSON of receipt *without* the signature field
    receipt["signature"] = sha256_hex(canonical_json(
        {k: v for k, v in receipt.items() if k != "signature"}
    ))

    return receipt


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="hermes-audit — Wrap a command with skill audit receipt generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  hermes-audit.py --skill ./skills/git-backup.SKILL.md --cmd "echo hello"
  hermes-audit.py --skill ./skill.md --cmd "ls -la" --output receipt.json
  hermes-audit.py --skill ./skill.md --cmd "sleep 1" --pretty

The receipt is printed to stdout unless --output is given.
""",
    )
    parser.add_argument(
        "--skill", "-s",
        required=True,
        help="Path to the SKILL.md file for the skill being executed",
    )
    parser.add_argument(
        "--cmd", "-c",
        required=True,
        help="Shell command to execute (wrapped for audit)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Write receipt JSON to this file (default: stdout)",
    )
    parser.add_argument(
        "--pretty", "-p",
        action="store_true",
        help="Pretty-print the receipt JSON",
    )
    parser.add_argument(
        "--no-scan",
        action="store_true",
        help="Skip hermes-scan integration (rating will be 'F' / score 0)",
    )
    args = parser.parse_args()

    # ---- Resolve skill path ----
    skill_path = Path(args.skill).expanduser().resolve()

    # ---- Parse skill frontmatter ----
    parsed = parse_skill_frontmatter(str(skill_path))
    if not parsed["ok"]:
        print(f"ERROR: Cannot parse skill file: {parsed['error']}", file=sys.stderr)
        sys.exit(2)

    skill_fm: dict = parsed["fm"]  # type: ignore[assignment]

    # ---- Scan the skill ----
    if args.no_scan:
        scan_report = {
            "skill_id": skill_fm.get("skill_id"),
            "rating": "F",
            "score": 0,
        }
        print("WARNING: --no-scan flag set — rating defaulted to F/0", file=sys.stderr)
    else:
        scan_report = scan_skill(str(skill_path))

    # ---- Execute the command ----
    started_at = utc_now_iso()
    start_ts = time.monotonic()

    try:
        proc = subprocess.run(
            args.cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,  # 5-minute default timeout for wrapped commands
            env=os.environ.copy(),
        )
        exit_code = proc.returncode
        stdout_text = proc.stdout
        stderr_text = proc.stderr
        run_error = None
    except subprocess.TimeoutExpired as exc:
        exit_code = -1
        stdout_text = exc.stdout or "" if hasattr(exc, "stdout") else ""
        stderr_text = exc.stderr or "" if hasattr(exc, "stderr") else ""
        run_error = f"Command timed out after 300s"
    except FileNotFoundError as exc:
        exit_code = -2
        stdout_text = ""
        stderr_text = str(exc)
        run_error = f"Command not found: {exc}"
    except Exception as exc:
        exit_code = -3
        stdout_text = ""
        stderr_text = str(exc)
        run_error = f"Command execution failed: {exc}"

    end_ts = time.monotonic()
    completed_at = utc_now_iso()
    duration_ms = int((end_ts - start_ts) * 1000)

    # Derive status from exit code
    if run_error:
        status = "error"
    elif exit_code == 0:
        status = "success"
    else:
        status = "failure"

    # If there was a run_error we didn't capture in stderr, append it
    if run_error and run_error not in stderr_text:
        stderr_text = (stderr_text + "\n" + run_error).strip()

    # ---- Build receipt ----
    receipt = build_receipt(
        skill_fm=skill_fm,
        scan_report=scan_report,
        command=args.cmd,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
        exit_code=exit_code,
        status=status,
        stdout_text=stdout_text,
        stderr_text=stderr_text,
    )

    # ---- Output ----
    indent = 2 if args.pretty else None
    receipt_json = json.dumps(receipt, indent=indent, ensure_ascii=False, default=str)

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(receipt_json + "\n", encoding="utf-8")
        print(f"Receipt written to {output_path}", file=sys.stderr)
    else:
        print(receipt_json)

    # Exit with the wrapped command's exit code (or 1 on error)
    if run_error:
        sys.exit(1)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
