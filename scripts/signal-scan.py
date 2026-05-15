#!/usr/bin/env python3
"""
signal-scan.py — Discovery Board 每日信号扫描

从 GitHub trending + Hacker News 自动抓取信号，产出结构化摘要。

Usage:
    python signal-scan.py                    # 扫描并输出到 stdout
    python signal-scan.py --output <path>    # 扫描并写入文件
    python signal-scan.py --json             # JSON 格式输出

Cron: 每日 08:00 自动运行，产出到 os/active/signals/
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

# Only stdlib imports — zero external deps
import urllib.request
import urllib.error

# ============================================================================
# Paths
# ============================================================================
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent if SCRIPT_DIR.name == "scripts" else Path.cwd()
SIGNALS_DIR = PROJECT_ROOT / "os" / "active" / "signals"

# ============================================================================
# Signal Sources
# ============================================================================

def _fetch_github_trending(per_page: int = 10) -> list[dict]:
    """Fetch trending repos from GitHub (created in last 24h)."""
    # Use the search API — repos created in last 2 days, sorted by stars
    url = (
        "https://api.github.com/search/repositories"
        "?q=created:>" + _iso_date(days_ago=2) +
        "&sort=stars&order=desc&per_page=" + str(per_page)
    )
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "hermes-signal-scan"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            items = data.get("items", [])
            return [
                {
                    "source": "github",
                    "title": item.get("full_name", ""),
                    "url": item.get("html_url", ""),
                    "description": (item.get("description") or "")[:200],
                    "stars": item.get("stargazers_count", 0),
                    "language": item.get("language", ""),
                    "topics": item.get("topics", [])[:5],
                    "signal_strength": _strength_from_stars(item.get("stargazers_count", 0)),
                }
                for item in items
            ]
    except Exception as e:
        return [{"source": "github", "error": str(e)}]


def _fetch_hackernews_top(top_n: int = 10) -> list[dict]:
    """Fetch top Hacker News stories."""
    try:
        # Get top story IDs
        url_ids = "https://hacker-news.firebaseio.com/v0/topstories.json"
        with urllib.request.urlopen(url_ids, timeout=10) as resp:
            ids = json.loads(resp.read().decode())[:top_n]

        stories = []
        for story_id in ids[:top_n]:
            try:
                url_item = f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
                with urllib.request.urlopen(url_item, timeout=10) as resp2:
                    item = json.loads(resp2.read().decode())
                    stories.append({
                        "source": "hackernews",
                        "title": item.get("title", ""),
                        "url": item.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
                        "score": item.get("score", 0),
                        "comments": item.get("descendants", 0),
                        "signal_strength": _strength_from_score(item.get("score", 0)),
                    })
            except Exception:
                continue
        return stories
    except Exception as e:
        return [{"source": "hackernews", "error": str(e)}]


def _iso_date(days_ago: int = 0) -> str:
    """ISO date string for N days ago."""
    from datetime import timedelta
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%d")


def _strength_from_stars(stars: int) -> str:
    if stars >= 5000:
        return "critical"
    if stars >= 1000:
        return "high"
    if stars >= 100:
        return "medium"
    return "low"


def _strength_from_score(score: int) -> str:
    if score >= 500:
        return "high"
    if score >= 100:
        return "medium"
    return "low"


# ============================================================================
# Signal Analysis
# ============================================================================

HERMES_KEYWORDS: list[str] = [
    "agent", "memory", "skill", "orchestrat", "multi-agent",
    "claude", "codex", "openclaw", "hermes", "mcp",
    "tool calling", "function call", "plugin", "registry",
    "llm", "ai agent", "autonomous", "workflow",
]


def _is_hermes_relevant(signal: dict) -> tuple[bool, list[str]]:
    """Check if a signal is relevant to Hermes ecosystem."""
    text = (
        (signal.get("title") or "") + " " +
        (signal.get("description") or "") + " " +
        " ".join(signal.get("topics", []))
    ).lower()
    matched = [kw for kw in HERMES_KEYWORDS if kw.lower() in text]
    return bool(matched), matched


# ============================================================================
# Main
# ============================================================================

def scan_signals(gh_per_page: int = 10, hn_top: int = 10) -> dict:
    """Run full signal scan and return structured results."""
    signals: list[dict] = []
    errors: list[str] = []

    # GitHub
    gh = _fetch_github_trending(gh_per_page)
    for item in gh:
        if "error" in item:
            errors.append(f"github: {item['error']}")
        else:
            relevant, keywords = _is_hermes_relevant(item)
            item["hermes_relevant"] = relevant
            item["matched_keywords"] = keywords
            signals.append(item)

    # HN
    hn = _fetch_hackernews_top(hn_top)
    for item in hn:
        if "error" in item:
            errors.append(f"hackernews: {item['error']}")
        else:
            relevant, keywords = _is_hermes_relevant(item)
            item["hermes_relevant"] = relevant
            item["matched_keywords"] = keywords
            signals.append(item)

    relevant_count = sum(1 for s in signals if s.get("hermes_relevant"))
    critical_count = sum(1 for s in signals if s.get("signal_strength") == "critical")

    return {
        "scan_id": f"signal-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}",
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "github": len([s for s in signals if s.get("source") == "github"]),
            "hackernews": len([s for s in signals if s.get("source") == "hackernews"]),
        },
        "total_signals": len(signals),
        "hermes_relevant": relevant_count,
        "critical": critical_count,
        "signals": signals,
        "errors": errors,
    }


def format_markdown(results: dict) -> str:
    """Format scan results as Markdown (for daily-ops injection)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Signal Scan — {now}",
        f"",
        f"**Sources**: GitHub ({results['sources']['github']}) + Hacker News ({results['sources']['hackernews']})",
        f"**Total**: {results['total_signals']} signals · {results['hermes_relevant']} relevant · {results['critical']} critical",
        f"",
    ]

    # Relevant signals first
    relevant = [s for s in results["signals"] if s.get("hermes_relevant")]
    if relevant:
        lines.append("## 🔴 Hermes-Relevant Signals")
        lines.append("")
        for s in relevant:
            strength = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}.get(s.get("signal_strength", ""), "")
            lines.append(f"### {strength} [{s.get('signal_strength', '').upper()}] {s.get('title', '?')}")
            lines.append(f"- **Source**: {s.get('source', '?')} | Stars: {s.get('stars', '-')} | Score: {s.get('score', '-')}")
            if s.get("description"):
                lines.append(f"- {s['description'][:200]}")
            if s.get("matched_keywords"):
                lines.append(f"- Matched: {', '.join(s['matched_keywords'][:5])}")
            if s.get("url"):
                lines.append(f"- {s['url']}")
            lines.append("")

    # All signals table
    lines.append("## 📋 Full Scan")
    lines.append("")
    lines.append("| Source | Title | Stars/Score | Strength | Relevant |")
    lines.append("|---|---|---|---|---|")
    for s in results["signals"]:
        metric = f"⭐{s.get('stars', s.get('score', '-'))} "
        strength_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}.get(s.get("signal_strength", ""), "")
        relevant_icon = "✅" if s.get("hermes_relevant") else ""
        title = (s.get("title") or "?")[:60]
        lines.append(f"| {s.get('source', '?')} | {title} | {metric} | {strength_icon} | {relevant_icon} |")

    if results["errors"]:
        lines.append("")
        lines.append("## ⚠️ Errors")
        for e in results["errors"]:
            lines.append(f"- {e}")

    lines.append("")
    lines.append("---")
    lines.append(f"*Generated by signal-scan.py · {now}*")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermes Discovery — Signal Scanner")
    parser.add_argument("--output", "-o", help="Write output to file")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--gh-count", type=int, default=10, help="GitHub repos to fetch")
    parser.add_argument("--hn-count", type=int, default=10, help="HN stories to fetch")
    args = parser.parse_args()

    print("🔍 Scanning signals...", file=sys.stderr)
    results = scan_signals(gh_per_page=args.gh_count, hn_top=args.hn_count)

    if args.json:
        output = json.dumps(results, ensure_ascii=False, indent=2)
    else:
        output = format_markdown(results)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"✓ Written: {out_path}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
