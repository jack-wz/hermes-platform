#!/usr/bin/env python3
"""
hermes scan — Static security analyzer for SKILL.md v1.0 files

Parses SKILL.md files with YAML frontmatter, validates against the v1.0 spec
defined in build/phase1/SKILL.md.v1.spec.md, and rates them A-F for security
and completeness.

Usage:
    hermes-scan.py <file.SKILL.md>
    hermes-scan.py --pretty <file.SKILL.md>
    hermes-scan.py --summary <file.SKILL.md>

Dependencies: PyYAML (pip install pyyaml)
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Constants from the SKILL.md v1.0 spec
# ---------------------------------------------------------------------------

MANDATORY_FIELDS = [
    "skill_id", "version", "author", "description",
    "permissions", "cost", "input", "output"
]

# Known / recognised Hermes tool names for tools validation
KNOWN_TOOLS = {
    "terminal", "file", "browser", "webhook", "database",
    "cache", "cron", "email", "http", "image", "audio", "video",
}

VALID_API_COST_RISKS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

VALID_INPUT_TYPES = {"string", "number", "boolean", "array", "object"}

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

# skill_id: {domain}/{category}/{name} or {namespace}/{name}
# lowercase, digits, hyphens, dots, underscores, slashes. Max 128 chars.
SKILL_ID_RE = re.compile(
    r"^[a-z0-9]([a-z0-9._/-]*[a-z0-9])?$"
)


# ---------------------------------------------------------------------------
# Parsing
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


def parse_frontmatter(filepath: str) -> tuple[Optional[dict], Optional[str], list[dict]]:
    """Parse YAML frontmatter from a SKILL.md file.

    Returns:
        (frontmatter_dict | None, body_text | None, parse_findings)
    """
    findings: list[dict] = []

    # Read file ----------------------------------------------------------
    try:
        content = Path(filepath).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, None, [
            {"severity": "error", "category": "structure",
             "message": f"File not found: {filepath}"}
        ]
    except Exception as exc:
        return None, None, [
            {"severity": "error", "category": "structure",
             "message": f"Cannot read file: {exc}"}
        ]

    lines = content.split("\n")

    # Detect frontmatter delimiters --------------------------------------
    if not lines or lines[0].strip() != "---":
        return None, None, [
            {"severity": "error", "category": "structure",
             "message": "No YAML frontmatter found (file must start with ---)"}
        ]

    end_idx: Optional[int] = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return None, None, [
            {"severity": "error", "category": "structure",
             "message": "Unclosed frontmatter: missing closing ---"}
        ]

    frontmatter_text = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1:])

    # Parse YAML ---------------------------------------------------------
    yaml = _load_yaml()
    try:
        fm = yaml.safe_load(frontmatter_text)
    except Exception as exc:
        return None, body, [
            {"severity": "error", "category": "structure",
             "message": f"YAML parse error: {exc}"}
        ]

    if fm is None:
        return {}, body, [
            {"severity": "error", "category": "structure",
             "message": "Empty frontmatter (no key-value pairs)"}
        ]

    if not isinstance(fm, dict):
        return None, body, [
            {"severity": "error", "category": "structure",
             "message": "Frontmatter is not a YAML mapping (expected key: value pairs)"}
        ]

    return fm, body, findings


# ---------------------------------------------------------------------------
# Validators  (one category each, matching spec §4.1-4.3)
# ---------------------------------------------------------------------------

def validate_structure(fm: Optional[dict]) -> list[dict]:
    """§4.1  Structure validation."""
    findings: list[dict] = []

    if fm is None or not isinstance(fm, dict):
        findings.append({
            "severity": "error", "category": "structure",
            "message": "Cannot perform structure validation — frontmatter missing or unparseable"
        })
        return findings

    # --- mandatory field presence ---
    for field in MANDATORY_FIELDS:
        val = fm.get(field)
        empty = val is None or (isinstance(val, str) and val.strip() == "")
        if empty:
            findings.append({
                "severity": "error", "category": "structure",
                "message": f"Missing mandatory field: '{field}'"
            })

    # --- skill_id format ---
    sid = fm.get("skill_id")
    if sid and isinstance(sid, str):
        if len(sid) > 128:
            findings.append({
                "severity": "error", "category": "structure",
                "message": f"skill_id exceeds 128 characters (got {len(sid)})"
            })
        elif not SKILL_ID_RE.match(sid):
            findings.append({
                "severity": "error", "category": "structure",
                "message": f"skill_id '{sid}' does not match required format "
                           f"(expected: lowercase/path-like, e.g. devops/backup/git-auto-backup)"
            })

    # --- version format ---
    ver = fm.get("version")
    if ver is not None:
        ver_str = str(ver)
        if not SEMVER_RE.match(ver_str):
            findings.append({
                "severity": "error", "category": "structure",
                "message": f"version '{ver_str}' is not valid SemVer (expected: MAJOR.MINOR.PATCH)"
            })

    # --- description length ---
    desc = fm.get("description")
    if desc and isinstance(desc, str):
        dlen = len(desc)
        if dlen < 20:
            findings.append({
                "severity": "warn", "category": "structure",
                "message": f"description is too short ({dlen} chars, minimum 20)"
            })
        elif dlen > 500:
            findings.append({
                "severity": "warn", "category": "structure",
                "message": f"description is too long ({dlen} chars, maximum 500)"
            })

    # --- author basic check ---
    author = fm.get("author")
    if isinstance(author, str):
        if len(author.strip()) < 2:
            findings.append({
                "severity": "warn", "category": "structure",
                "message": "author string is too short (expected 'Name <email>' or structured object)"
            })
    elif author is None:
        pass  # caught by mandatory-field check
    elif not isinstance(author, dict):
        findings.append({
            "severity": "warn", "category": "structure",
            "message": f"author should be a string or object, got {type(author).__name__}"
        })

    return findings


def validate_security(fm: Optional[dict]) -> tuple[list[dict], dict]:
    """§4.2  Security validation.  Returns (findings, permission_analysis)."""
    findings: list[dict] = []
    analysis: dict = {"scope_score": 20, "issues": []}

    if fm is None or not isinstance(fm, dict):
        analysis["scope_score"] = 0
        analysis["issues"].append("No frontmatter to analyze permissions")
        findings.append({
            "severity": "error", "category": "security",
            "message": "Cannot perform security validation — frontmatter missing or unparseable"
        })
        return findings, analysis

    perms = fm.get("permissions")
    if not perms or not isinstance(perms, dict):
        findings.append({
            "severity": "error", "category": "security",
            "message": "permissions not declared or is not a mapping"
        })
        analysis["scope_score"] = 0
        analysis["issues"].append("No permissions declared")
        return findings, analysis

    # --- filesystem paths ---
    fs = perms.get("filesystem", {})
    if isinstance(fs, dict):
        for direction, label in [("read", "read"), ("write", "write")]:
            paths = fs.get(direction, [])
            if not isinstance(paths, list):
                continue
            for raw in paths:
                p = str(raw)
                # Root-level wildcards: /**, ~/**, /**/..., ~/**/..., /, ~
                is_root_wildcard = (
                    p in ("/**", "~/**", "/*", "~/*", "/", "~")
                    or p.startswith("/**/") or p.startswith("~/**/")
                )
                if is_root_wildcard:
                    analysis["scope_score"] = max(0, analysis["scope_score"] - 10)
                    analysis["issues"].append(
                        f"Dangerous {label} path: {p} (root-level wildcard grants broad access)"
                    )
                    findings.append({
                        "severity": "error", "category": "security",
                        "message": f"Root-level wildcard in {label} path: {p}"
                    })
                elif "**" in p:
                    # Directory-scoped wildcard — less dangerous but still overbroad
                    analysis["scope_score"] = max(0, analysis["scope_score"] - 2)
                    analysis["issues"].append(
                        f"Overbroad {label} path: {p} (directory-level wildcard)"
                    )
                    findings.append({
                        "severity": "warn", "category": "security",
                        "message": f"Directory-level wildcard in {label} path: {p}"
                    })
                elif "*" in p:
                    analysis["scope_score"] = max(0, analysis["scope_score"] - 1)
                    analysis["issues"].append(
                        f"Wildcard in {label} path: {p}"
                    )
                    findings.append({
                        "severity": "warn", "category": "security",
                        "message": f"Glob wildcard in {label} path: {p}"
                    })

    # --- network ---
    net = perms.get("network", {})
    if isinstance(net, dict):
        domains = net.get("domains", [])
        if isinstance(domains, list):
            for domain in domains:
                if str(domain).strip() == "*":
                    analysis["scope_score"] = max(0, analysis["scope_score"] - 10)
                    analysis["issues"].append("Network domain wildcard '*' — allows any domain")
                    findings.append({
                        "severity": "error", "category": "security",
                        "message": "Wildcard '*' in network.domains — allows connecting to any host"
                    })

        ports = net.get("ports", [])
        if isinstance(ports, list) and len(ports) == 0:
            findings.append({
                "severity": "warn", "category": "security",
                "message": "network declared but ports list is empty (no port restrictions)"
            })

        protocols = net.get("protocols", [])
        if isinstance(protocols, list) and len(protocols) == 0:
            findings.append({
                "severity": "warn", "category": "security",
                "message": "network declared but protocols list is empty (no protocol restrictions)"
            })

    # --- tools ---
    tools = perms.get("tools", [])
    if not isinstance(tools, list) or len(tools) == 0:
        findings.append({
            "severity": "error", "category": "security",
            "message": "permissions.tools is empty or missing — at least one tool must be declared"
        })
        analysis["scope_score"] = max(0, analysis["scope_score"] - 5)
    else:
        for tool in tools:
            if tool not in KNOWN_TOOLS:
                findings.append({
                    "severity": "warn", "category": "security",
                    "message": f"Unknown tool '{tool}' — not in recognised Hermes tools set"
                })

    # --- credentials ---
    creds = perms.get("credentials", [])
    if not isinstance(creds, list):
        findings.append({
            "severity": "error", "category": "security",
            "message": "permissions.credentials must be an array"
        })
        analysis["scope_score"] = max(0, analysis["scope_score"] - 5)
    elif len(creds) > 0:
        for cred in creds:
            if not isinstance(cred, dict):
                findings.append({
                    "severity": "error", "category": "security",
                    "message": "Each credential entry must be an object"
                })
                continue
            for key in ["name", "type", "scope"]:
                if key not in cred or cred[key] is None:
                    findings.append({
                        "severity": "error", "category": "security",
                        "message": f"Credential entry missing required field: '{key}'"
                    })

    # --- api_cost_risk ---
    cost = fm.get("cost", {})
    if isinstance(cost, dict):
        risk = cost.get("api_cost_risk")
        if risk is not None and str(risk).upper() not in VALID_API_COST_RISKS:
            findings.append({
                "severity": "error", "category": "security",
                "message": f"Invalid api_cost_risk '{risk}' — must be LOW | MEDIUM | HIGH | CRITICAL"
            })

    return findings, analysis


def validate_contract(fm: Optional[dict]) -> tuple[list[dict], dict]:
    """§4.3  Contract validation (input / output / cost)."""
    findings: list[dict] = []
    cost_analysis: dict = {"declared": False, "issues": []}

    if fm is None or not isinstance(fm, dict):
        return findings, cost_analysis

    # --- cost ---
    cost = fm.get("cost")
    if isinstance(cost, dict):
        cost_analysis["declared"] = True

        te = cost.get("token_estimate")
        if not isinstance(te, dict):
            cost_analysis["issues"].append("token_estimate missing or not an object")
            findings.append({
                "severity": "error", "category": "contract",
                "message": "cost.token_estimate is missing or is not an object"
            })
        else:
            if "base" not in te:
                cost_analysis["issues"].append("token_estimate.base missing")
                findings.append({
                    "severity": "warn", "category": "contract",
                    "message": "cost.token_estimate.base is missing"
                })
            per_run = te.get("per_run", {})
            if not isinstance(per_run, dict):
                cost_analysis["issues"].append("token_estimate.per_run missing or not an object")
                findings.append({
                    "severity": "warn", "category": "contract",
                    "message": "cost.token_estimate.per_run is missing or not an object"
                })
            elif "total" not in per_run:
                cost_analysis["issues"].append("token_estimate.per_run.total missing")
                findings.append({
                    "severity": "warn", "category": "contract",
                    "message": "cost.token_estimate.per_run.total is missing"
                })

        risk = cost.get("api_cost_risk")
        if risk is None:
            cost_analysis["issues"].append("api_cost_risk not declared")
            findings.append({
                "severity": "error", "category": "contract",
                "message": "cost.api_cost_risk is not declared"
            })
    else:
        cost_analysis["issues"].append("No cost declaration")
        findings.append({
            "severity": "error", "category": "contract",
            "message": "cost field is missing or invalid"
        })

    # --- input ---
    inp = fm.get("input")
    if isinstance(inp, dict):
        for section, label in [("required", "Required"), ("optional", "Optional")]:
            params = inp.get(section, [])
            if not isinstance(params, list):
                continue
            for param in params:
                if not isinstance(param, dict):
                    continue
                pname = param.get("name", "?")
                # type check
                ptype = param.get("type")
                if ptype is None:
                    findings.append({
                        "severity": "error", "category": "contract",
                        "message": f"{label} input '{pname}' is missing 'type'"
                    })
                elif ptype not in VALID_INPUT_TYPES:
                    findings.append({
                        "severity": "warn", "category": "contract",
                        "message": f"Input '{pname}' has unknown type '{ptype}' "
                                   f"(expected: {', '.join(sorted(VALID_INPUT_TYPES))})"
                    })
                # required: must have description
                if section == "required":
                    if not param.get("description"):
                        findings.append({
                            "severity": "warn", "category": "contract",
                            "message": f"Required input '{pname}' is missing 'description'"
                        })
                # optional: must have default
                if section == "optional":
                    if "default" not in param:
                        findings.append({
                            "severity": "warn", "category": "contract",
                            "message": f"Optional input '{pname}' is missing 'default' value"
                        })

    # --- output ---
    out = fm.get("output")
    if isinstance(out, dict):
        for key, label in [("success", "Success"), ("failure", "Failure")]:
            section = out.get(key)
            if not isinstance(section, dict):
                findings.append({
                    "severity": "error", "category": "contract",
                    "message": f"output.{key} is missing or not an object"
                })
                continue
            if not section.get("schema"):
                findings.append({
                    "severity": "error", "category": "contract",
                    "message": f"output.{key}.schema is missing — {label} output schema required"
                })

    return findings, cost_analysis


# ---------------------------------------------------------------------------
# Scoring  (A-F)
# ---------------------------------------------------------------------------

def compute_score(fm: Optional[dict], all_findings: list[dict],
                  perm_analysis: dict) -> tuple[int, str]:
    """Compute the numeric score (0-100) and letter grade (A-F).

    The scoring matrix matches the tier definitions from the Phase 2 spec:
        A (90-100): All mandatory fields, tightly scoped perms, full contracts
        B (75-89):  All mandatory fields, minor scope / optional-field gaps
        C (55-74):  All mandatory fields but overbroad perms, vague cost
        D (35-54):  Missing 1-2 mandatory fields OR dangerous perms
        E (15-34):  Missing 3+ mandatory fields, no cost
        F (0-14):   Unparseable, no perms at all
    """
    if fm is None or not isinstance(fm, dict):
        return 0, "F"

    score = 100

    # --- Missing mandatory fields (biggest factor) ---
    missing = [
        f for f in MANDATORY_FIELDS
        if f not in fm
        or fm[f] is None
        or (isinstance(fm[f], str) and fm[f].strip() == "")
        or (isinstance(fm[f], list) and len(fm[f]) == 0 and f == "permissions")
    ]
    missing_count = len(missing)

    if missing_count >= 5:
        score -= 60
    elif missing_count >= 3:
        score -= 45
    elif missing_count >= 1:
        score -= 15 * missing_count

    # --- Deductions from findings ---
    for finding in all_findings:
        sev = finding["severity"]
        msg = finding["message"]
        cat = finding["category"]

        if sev == "error":
            if cat == "structure":
                if "Missing mandatory field" in msg:
                    pass  # already handled above
                elif "skill_id" in msg:
                    score -= 5
                elif "version" in msg and "SemVer" in msg:
                    score -= 5
                elif "description is too short" in msg:
                    score -= 3
                elif "description is too long" in msg:
                    score -= 2
                else:
                    score -= 4

            elif cat == "security":
                if "Root-level wildcard" in msg:
                    score -= 12
                elif "Wildcard '*' in network" in msg:
                    score -= 10
                elif "tools is empty" in msg:
                    score -= 5
                elif "Credentials" in msg or "credential" in msg.lower():
                    score -= 3
                elif "Invalid api_cost_risk" in msg:
                    score -= 5
                elif "permissions not declared" in msg:
                    score -= 15
                else:
                    score -= 4

            elif cat == "contract":
                if "cost field is missing" in msg:
                    score -= 10
                elif "token_estimate is missing" in msg:
                    score -= 6
                elif "schema is missing" in msg:
                    score -= 5
                elif "missing 'type'" in msg:
                    score -= 3
                elif "api_cost_risk is not declared" in msg:
                    score -= 4
                else:
                    score -= 3

        elif sev == "warn":
            if cat == "security":
                if "Directory-level wildcard" in msg:
                    score -= 2
                elif "Glob wildcard" in msg:
                    score -= 1
                elif "Network declared" in msg or "ports list" in msg or "protocols list" in msg:
                    score -= 1
                elif "Unknown tool" in msg:
                    score -= 1
                else:
                    score -= 1
            elif cat == "contract":
                if "missing 'description'" in msg:
                    score -= 1
                elif "missing 'default'" in msg:
                    score -= 1
                elif "unknown type" in msg:
                    score -= 1
                elif "base is missing" in msg or "total is missing" in msg:
                    score -= 2
            elif cat == "structure":
                if "too short" in msg or "too long" in msg:
                    score -= 1
                elif "author" in msg:
                    score -= 1

    # Scope score maps directly: 0-20 range, deducted from total
    scope_deduction = max(0, 20 - perm_analysis.get("scope_score", 20))
    score -= scope_deduction

    # Clamp and rate
    score = max(0, min(100, score))

    if score >= 90:
        rating = "A"
    elif score >= 75:
        rating = "B"
    elif score >= 55:
        rating = "C"
    elif score >= 35:
        rating = "D"
    elif score >= 15:
        rating = "E"
    else:
        rating = "F"

    return score, rating


# ---------------------------------------------------------------------------
# Top-level scanner
# ---------------------------------------------------------------------------

def scan_file(filepath: str) -> dict:
    """Run all validators against a single SKILL.md file.

    Returns the structured JSON report defined in the Phase 2 spec.
    """
    fm, body, parse_findings = parse_frontmatter(filepath)

    # --- Unrecoverable?  Short-circuit to F ---
    fatal_messages = {
        "No YAML frontmatter", "Unclosed frontmatter",
        "YAML parse error", "Empty frontmatter",
        "not a YAML mapping", "Cannot read file", "File not found",
    }
    is_fatal = any(
        any(phrase in f["message"] for phrase in fatal_messages)
        for f in parse_findings
    )
    if is_fatal:
        return {
            "skill_id": None,
            "rating": "F",
            "score": 0,
            "findings": parse_findings,
            "mandatory_check": {"present": [], "missing": MANDATORY_FIELDS},
            "permission_analysis": {
                "scope_score": 0,
                "issues": ["Frontmatter unparseable — cannot analyze permissions"]
            },
            "cost_analysis": {
                "declared": False,
                "issues": ["Frontmatter unparseable — cannot analyze cost"]
            },
        }

    # --- Gather all findings ---
    all_findings: list[dict] = list(parse_findings)
    all_findings.extend(validate_structure(fm))
    sec_findings, perm_analysis = validate_security(fm)
    all_findings.extend(sec_findings)
    con_findings, cost_analysis = validate_contract(fm)
    all_findings.extend(con_findings)

    # --- Mandatory field summary ---
    present: list[str] = []
    missing: list[str] = []
    if isinstance(fm, dict):
        for field in MANDATORY_FIELDS:
            val = fm.get(field)
            empty = (
                val is None
                or (isinstance(val, str) and val.strip() == "")
                or (isinstance(val, list) and len(val) == 0 and field == "permissions")
            )
            (missing if empty else present).append(field)
    else:
        missing = list(MANDATORY_FIELDS)

    # --- Score ---
    score, rating = compute_score(fm, all_findings, perm_analysis)

    skill_id = fm.get("skill_id") if isinstance(fm, dict) else None

    return {
        "skill_id": skill_id,
        "rating": rating,
        "score": score,
        "findings": all_findings,
        "mandatory_check": {"present": present, "missing": missing},
        "permission_analysis": perm_analysis,
        "cost_analysis": cost_analysis,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="hermes scan — Static security analyzer for SKILL.md v1.0 files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  hermes-scan.py skill.SKILL.md
  hermes-scan.py --pretty skill.SKILL.md
  hermes-scan.py --summary skill.SKILL.md
        """,
    )
    parser.add_argument(
        "file", help="Path to the SKILL.md file to scan"
    )
    parser.add_argument(
        "--pretty", "-p", action="store_true",
        help="Pretty-print the JSON output"
    )
    parser.add_argument(
        "--summary", "-s", action="store_true",
        help="Print a human-readable summary instead of JSON"
    )
    args = parser.parse_args()

    report = scan_file(args.file)

    if args.summary:
        errors = [f for f in report["findings"] if f["severity"] == "error"]
        warns = [f for f in report["findings"] if f["severity"] == "warn"]
        infos = [f for f in report["findings"] if f["severity"] == "info"]

        print(f"Rating:  {report['rating']}  ({report['score']}/100)")
        print(f"Skill:   {report['skill_id'] or '(unknown)'}")
        print(f"File:    {args.file}")
        print(f"Errors:  {len(errors)}   Warnings: {len(warns)}   Info: {len(infos)}")
        print(f"Mandatory fields — present: {report['mandatory_check']['present']}")
        if report["mandatory_check"]["missing"]:
            print(f"                  missing: {report['mandatory_check']['missing']}")
        print(f"Permissions scope score: {report['permission_analysis']['scope_score']}/20")
        if report["permission_analysis"]["issues"]:
            for issue in report["permission_analysis"]["issues"]:
                print(f"  • {issue}")
        print(f"Cost declared: {report['cost_analysis']['declared']}")
        if report["cost_analysis"]["issues"]:
            for issue in report["cost_analysis"]["issues"]:
                print(f"  • {issue}")

        if errors:
            print(f"\nAll errors ({len(errors)}):")
            for e in errors:
                print(f"  [{e['category']}] {e['message']}")
        if warns:
            print(f"\nAll warnings ({len(warns)}):")
            for w in warns:
                print(f"  [{w['category']}] {w['message']}")
    else:
        indent = 2 if args.pretty else None
        print(json.dumps(report, indent=indent, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
