#!/usr/bin/env python3
"""
hermes-convert — Convert any GitHub project to SKILL.md format.

Supports:
  - GitHub repo → SKILL.md (reads README as body, metadata from API)
  - Claude Code skill → SKILL.md (CLAUDE.md → SKILL.md frontmatter)
  - Plain README → SKILL.md (wraps with inferred metadata)

Usage:
  hermes-convert.py github mikesheehan54/Claude-Code-Design-AI
  hermes-convert.py claude path/to/CLAUDE.md
  hermes-convert.py readme path/to/README.md --name "my-skill" --author "me"
"""

import argparse
import json
import re
import sys
import urllib.request
import base64
from datetime import datetime, timezone
from pathlib import Path

UA = "Mozilla/5.0"


def _infer_tags(desc: str, topics: list[str]) -> list[str]:
    """Infer tags from description and GitHub topics."""
    tags = list(topics)[:5]
    keywords = {
        "design": "design", "ui": "ui", "ux": "ux", "react": "react",
        "tailwind": "tailwind", "figma": "figma", "component": "components",
        "ai": "ai", "agent": "agent", "skill": "skill", "claude": "claude",
        "codex": "codex", "copilot": "copilot", "mcp": "mcp",
        "automation": "automation", "memory": "memory", "governance": "governance",
    }
    for word, tag in keywords.items():
        if word in desc.lower() and tag not in tags:
            tags.append(tag)
    return tags[:8]


def _estimate_security(desc: str, topics: list[str]) -> dict:
    """Estimate security metadata from project description."""
    has_network = any(k in desc.lower() for k in ["api", "fetch", "http", "request", "mcp"])
    has_filesystem = any(k in desc.lower() for k in ["file", "write", "read", "save", "export"])
    
    return {
        "permissions": (
            ["network-outbound"] if has_network else []
        ) + (["file-read", "file-write"] if has_filesystem else []),
        "max_cost_estimate": 0.05,
        "network_domains": ["api.github.com"] if has_network else [],
        "filesystem_scope": ["./"] if has_filesystem else [],
        "requires_approval": has_network,
    }


def convert_github(args: argparse.Namespace) -> int:
    """Convert a GitHub repo to SKILL.md."""
    ref = args.repo.strip().rstrip("/")
    match = re.match(r"(?:https?://github\.com/)?([^/]+)/([^/]+?)(?:\.git)?$", ref)
    if not match:
        print(f"ERROR: Invalid GitHub repo reference: {ref}", file=sys.stderr)
        return 1
    
    owner, repo_name = match.group(1), match.group(2)
    print(f"📦 Converting {owner}/{repo_name} → SKILL.md...")
    
    # Fetch repo metadata
    try:
        url = f"https://api.github.com/repos/{owner}/{repo_name}"
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github.v3+json"})
        repo = json.loads(urllib.request.urlopen(req, timeout=10).read())
    except Exception as e:
        print(f"ERROR: Cannot fetch repo: {e}", file=sys.stderr)
        return 1
    
    # Fetch README
    readme_content = ""
    try:
        url2 = f"https://api.github.com/repos/{owner}/{repo_name}/readme"
        req2 = urllib.request.Request(url2, headers={"User-Agent": UA, "Accept": "application/vnd.github.v3+json"})
        resp2 = json.loads(urllib.request.urlopen(req2, timeout=10).read())
        readme_content = base64.b64decode(resp2["content"]).decode("utf-8")
    except Exception:
        readme_content = repo.get("description", "")
    
    # Build SKILL.md
    name = repo_name.lower().replace(" ", "-")
    desc = repo.get("description", "")[:200]
    tags = _infer_tags(desc, repo.get("topics", []))
    security = _estimate_security(desc, repo.get("topics", []))
    stars = repo.get("stargazers_count", 0)
    
    skill_id = f"github/{owner}/{name}"
    
    frontmatter = f"""---
name: {name}
skill_id: {skill_id}
version: 1.0.0
description: "{desc}"
author: {owner}
source: {repo.get("html_url")}
license: {repo.get("license", {}).get("spdx_id", "Unknown")}
stars: {stars}
tags: {json.dumps(tags)}

security:
  permissions: {json.dumps(security["permissions"])}
  max_cost_estimate: {security["max_cost_estimate"]}
  network_domains: {json.dumps(security["network_domains"])}
  filesystem_scope: {json.dumps(security["filesystem_scope"])}
  requires_approval: {str(security["requires_approval"]).lower()}

runtime:
  min_tokens: 500
  max_tokens: 8000
  timeout_seconds: 120

converted:
  from: github
  original_repo: {owner}/{repo_name}
  converted_at: {datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
---
"""

    skill_md = frontmatter + "\n# " + (repo.get("name", name)) + "\n\n" + readme_content
    
    # Write
    output_path = Path(args.output) if hasattr(args, 'output') else Path(f"{name}.SKILL.md")
    Path(args.output).write_text(skill_md, encoding="utf-8") if hasattr(args, 'output') else print(skill_md)
    
    print(f"✅ Converted: {skill_id}")
    print(f"   Stars: {stars}★  License: {repo.get('license', {}).get('spdx_id', 'N/A')}")
    print(f"   Tags: {', '.join(tags)}")
    print(f"   Permissions: {', '.join(security['permissions']) if security['permissions'] else 'none'}")
    
    if not hasattr(args, 'output'):
        print(f"\n   Save with: hermes-convert.py github {ref} --output {name}.SKILL.md")
    
    return 0


def convert_claude(args: argparse.Namespace) -> int:
    """Convert a Claude Code CLAUDE.md skill to SKILL.md."""
    path = Path(args.path).expanduser()
    if not path.exists():
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        return 1
    
    content = path.read_text(encoding="utf-8")
    name = path.parent.name if path.name == "CLAUDE.md" else path.stem
    
    # Try to extract description from first paragraph
    lines = content.strip().split("\n")
    desc = ""
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("<!--"):
            desc = stripped[:200]
            break
    
    frontmatter = f"""---
name: {name.lower().replace(" ", "-")}
skill_id: claude/{name.lower().replace(" ", "-")}
version: 1.0.0
description: {desc}
author: claude-skill
source: file://{path}
license: Unknown
tags: [claude, skill]

security:
  permissions: []
  max_cost_estimate: 0.05
  network_domains: []
  filesystem_scope: []
  requires_approval: false

runtime:
  min_tokens: 500
  max_tokens: 8000
  timeout_seconds: 120

converted:
  from: claude
  original_file: {path.name}
  converted_at: {datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
---
"""
    
    skill_md = frontmatter + "\n" + content
    print(skill_md)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert projects to SKILL.md format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  hermes-convert.py github mikesheehan54/Claude-Code-Design-AI
  hermes-convert.py github mikesheehan54/Claude-Code-Design-AI --output Design.SKILL.md
  hermes-convert.py claude path/to/CLAUDE.md
""",
    )
    sub = parser.add_subparsers(dest="command")
    
    p_gh = sub.add_parser("github", help="Convert GitHub repo to SKILL.md")
    p_gh.add_argument("repo", help="GitHub repo (owner/repo or URL)")
    p_gh.add_argument("--output", "-o", help="Output file path (default: stdout)")
    
    p_claude = sub.add_parser("claude", help="Convert Claude Code skill")
    p_claude.add_argument("path", help="Path to CLAUDE.md")
    
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1
    
    if args.command == "github":
        return convert_github(args)
    elif args.command == "claude":
        return convert_claude(args)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
