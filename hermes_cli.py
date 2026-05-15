#!/usr/bin/env python3
"""
hermes — Unified CLI for Hermes Workspace
==========================================

Single entry point for all Hermes tools:

    hermes serve          Start Dashboard + Connector servers
    hermes registry       Manage skill registry (list/search/install/publish)
    hermes coworker       Manage AI coworkers (list/run)
    hermes memory         Manage shared memory (add/search/context)
    hermes scan           Scan a skill for security
    hermes audit          Generate execution audit receipt
    hermes sandbox        Test a skill in isolated sandbox
    hermes connect        Multi-channel connector (send/platforms/serve)
    hermes convert        Convert project to SKILL.md format
    hermes marketplace    Start Marketplace API server

Install: pip install hermes-workspace
"""

import argparse
import importlib.resources
import json
import os
import subprocess
import sys
from pathlib import Path

# Resolve package root: works in both dev (repo root) and installed (site-packages) mode
_PKG_FILE = Path(__file__).resolve()
if (_PKG_FILE.parent / "build").exists():
    # Dev mode: running from repo root
    PACKAGE_DIR = _PKG_FILE.parent
else:
    # Installed mode: find the repo root relative to site-packages
    PACKAGE_DIR = _PKG_FILE.parent.parent.parent.parent  # site-packages/hermes_cli.py → project root
BUILD_DIR = PACKAGE_DIR / "build"
REGISTRY_FILE = PACKAGE_DIR / "registry" / "skills.json"


def _load_registry() -> dict:
    if not REGISTRY_FILE.exists():
        return {"skills": []}
    with open(REGISTRY_FILE) as f:
        return json.load(f)


def _run_script(script_rel_path: str, *args: str) -> int:
    """Run a Hermes script with given arguments."""
    script = BUILD_DIR / script_rel_path
    if not script.exists():
        print(f"ERROR: Script not found: {script}", file=sys.stderr)
        return 1
    return subprocess.run(
        [sys.executable, str(script)] + list(args),
        cwd=str(PACKAGE_DIR),
    ).returncode


def cmd_serve(args: argparse.Namespace) -> int:
    """Start the Hermes Dashboard server."""
    return _run_script("workspace/hermes-dashboard.py")


def cmd_registry(args: argparse.Namespace) -> int:
    """Registry management — delegates to hermes-registry.py."""
    registry_args = []
    if hasattr(args, 'subcommand'):
        registry_args.append(args.subcommand)
        if hasattr(args, 'skill_ref') and args.skill_ref:
            registry_args.append(args.skill_ref)
        if hasattr(args, 'query') and args.query:
            registry_args.append(args.query)
        if hasattr(args, 'skill_path') and args.skill_path:
            registry_args.append(args.skill_path)
        if hasattr(args, 'port') and args.port:
            registry_args.extend(["--port", str(args.port)])
        if hasattr(args, 'format') and args.format:
            registry_args.extend(["--format", args.format])
    return _run_script("phase5/hermes-registry.py", *registry_args)


def cmd_memory(args: argparse.Namespace) -> int:
    """Memory management."""
    mem_args = [args.subcommand] if hasattr(args, 'subcommand') else []
    if hasattr(args, 'entry') and args.entry:
        mem_args.append(args.entry)
    if hasattr(args, 'author') and args.author:
        mem_args.extend(["--author", args.author])
    if hasattr(args, 'query') and args.query:
        mem_args.append(args.query)
    return _run_script("workspace/hermes-memory.py", *mem_args)


def cmd_scan(args: argparse.Namespace) -> int:
    return _run_script("phase2/hermes-scan.py", args.skill_path, "--json" if args.json else "")


def cmd_audit(args: argparse.Namespace) -> int:
    audit_args = ["--skill", args.skill_path]
    if args.run_id:
        audit_args.extend(["--run-id", args.run_id])
    return _run_script("phase3/hermes-audit.py", *audit_args)


def cmd_sandbox(args: argparse.Namespace) -> int:
    sandbox_args = ["test", args.skill_path]
    if args.timeout:
        sandbox_args.extend(["--timeout", str(args.timeout)])
    if args.json:
        sandbox_args.append("--json")
    return _run_script("phase5/hermes-sandbox.py", *sandbox_args)


def cmd_coworker(args: argparse.Namespace) -> int:
    coworker_args = [args.subcommand] if hasattr(args, 'subcommand') else ["list"]
    if hasattr(args, 'coworker_id') and args.coworker_id:
        coworker_args.append(args.coworker_id)
    return _run_script("workspace/hermes-coworker.py", *coworker_args)


def cmd_connect(args: argparse.Namespace) -> int:
    conn_args = []
    if hasattr(args, 'subcommand'):
        conn_args.append(args.subcommand)
    if hasattr(args, 'platform') and args.platform:
        conn_args.extend(["--platform", args.platform])
    if hasattr(args, 'channel') and args.channel:
        conn_args.extend(["--channel", args.channel])
    if hasattr(args, 'text') and args.text:
        conn_args.extend(["--text", args.text])
    if hasattr(args, 'port') and args.port:
        conn_args.extend(["--port", str(args.port)])
    return _run_script("phase5/hermes-connector.py", *conn_args)


def cmd_convert(args: argparse.Namespace) -> int:
    conv_args = ["github", args.repo]
    if args.output:
        conv_args.extend(["--output", args.output])
    return _run_script("phase5/hermes-convert.py", *conv_args)


def cmd_marketplace(args: argparse.Namespace) -> int:
    return _run_script("phase5/hermes-registry.py", "marketplace", "--port", str(args.port or 5003))


def cmd_version(args: argparse.Namespace) -> int:
    print("Hermes Workspace v2.0.0")
    print("  Platform:  SKILL.md v1 + scan + audit + Plugin Bridge")
    registry = _load_registry()
    skill_count = len(registry.get("skills", []))
    print(f"  Registry:  {skill_count} skills")
    print("  Coworkers: 8 pre-built (ops × 3, sales × 2, marketing × 1, legal × 1, hr × 1)")
    print("  Memory:    v1.2 with namespace isolation + GateMem export")
    print("  Channels:  Feishu, Slack, Discord (connector framework)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hermes Workspace — Open-source AI team workspace",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Quick Start:
  hermes serve              Start Dashboard at http://localhost:5002
  hermes registry list      List registered skills
  hermes memory add "note"  Add shared memory
  hermes scan skill.md      Security scan a skill
  hermes sandbox skill.md   Test a skill in sandbox"""

    )
    sub = parser.add_subparsers(dest="command")

    # serve
    sub.add_parser("serve", help="Start Dashboard server (port 5002)")

    # registry
    p_reg = sub.add_parser("registry", help="Skill registry management")
    p_reg_sub = p_reg.add_subparsers(dest="subcommand")
    p_reg_sub.add_parser("list", help="List all skills")
    p_reg_s = p_reg_sub.add_parser("search", help="Search skills")
    p_reg_s.add_argument("query")
    p_reg_i = p_reg_sub.add_parser("install", help="Install skill from GitHub")
    p_reg_i.add_argument("skill_ref")
    p_reg_p = p_reg_sub.add_parser("publish", help="Publish skill")
    p_reg_p.add_argument("skill_path")
    p_reg_sub.add_parser("stats", help="Registry statistics")
    p_reg_m = p_reg_sub.add_parser("marketplace", help="Start Marketplace API")
    p_reg_m.add_argument("--port", type=int, default=5003)

    # memory
    p_mem = sub.add_parser("memory", help="Shared memory management")
    p_mem_sub = p_mem.add_subparsers(dest="subcommand")
    p_mem_sub.add_parser("show", help="Display all memory")
    p_mem_a = p_mem_sub.add_parser("add", help="Add memory entry")
    p_mem_a.add_argument("entry")
    p_mem_a.add_argument("--author", "-a", default="human")
    p_mem_s = p_mem_sub.add_parser("search", help="Search memory")
    p_mem_s.add_argument("query")
    p_mem_sub.add_parser("context", help="Get compressed context")
    p_mem_sub.add_parser("namespaces", help="List namespaces")

    # scan
    p_scan = sub.add_parser("scan", help="Security scan a skill")
    p_scan.add_argument("skill_path")
    p_scan.add_argument("--json", action="store_true")

    # audit
    p_audit = sub.add_parser("audit", help="Generate audit receipt")
    p_audit.add_argument("skill_path")
    p_audit.add_argument("--run-id")

    # sandbox
    p_sand = sub.add_parser("sandbox", help="Test skill in isolated sandbox")
    p_sand.add_argument("skill_path")
    p_sand.add_argument("--timeout", type=int, default=30)
    p_sand.add_argument("--json", action="store_true")

    # coworker
    p_cow = sub.add_parser("coworker", help="AI coworker management")
    p_cow_sub = p_cow.add_subparsers(dest="subcommand")
    p_cow_sub.add_parser("list", help="List all coworkers")
    p_cow_r = p_cow_sub.add_parser("run", help="Run a coworker")
    p_cow_r.add_argument("coworker_id")

    # connect
    p_conn = sub.add_parser("connect", help="Multi-channel connector")
    p_conn_sub = p_conn.add_subparsers(dest="subcommand")
    p_conn_sub.add_parser("platforms", help="List configured platforms")
    p_conn_s = p_conn_sub.add_parser("send", help="Send message")
    p_conn_s.add_argument("--platform", "-p", required=True)
    p_conn_s.add_argument("--channel", "-c", required=True)
    p_conn_s.add_argument("--text", "-t", required=True)
    p_conn_srv = p_conn_sub.add_parser("serve", help="Start connector server")
    p_conn_srv.add_argument("--port", type=int, default=5004)

    # convert
    p_conv = sub.add_parser("convert", help="Convert project to SKILL.md")
    p_conv.add_argument("repo")
    p_conv.add_argument("--output", "-o")

    # marketplace (shortcut)
    p_mkt = sub.add_parser("marketplace", help="Start Marketplace API server")
    p_mkt.add_argument("--port", type=int, default=5003)

    # version
    sub.add_parser("version", help="Show version info")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "serve": cmd_serve,
        "registry": cmd_registry,
        "memory": cmd_memory,
        "scan": cmd_scan,
        "audit": cmd_audit,
        "sandbox": cmd_sandbox,
        "coworker": cmd_coworker,
        "connect": cmd_connect,
        "convert": cmd_convert,
        "marketplace": cmd_marketplace,
        "version": cmd_version,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
