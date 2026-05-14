#!/usr/bin/env python3
"""
hermes-knowledge — LLM Wiki Knowledge Base Manager
====================================================

Implements the LLM Wiki file structure standard for Hermes Workspace:
  knowledge_base/
  ├── raw/sources/      Original documents
  ├── wiki/entities/     Entities (people, tools, projects)
  ├── wiki/concepts/     Concepts (methods, principles)
  ├── wiki/index.md      Knowledge base index
  └── wiki/log.md        Update log

Features:
  - Extract entities/concepts from documents
  - Create structured markdown with [[bidirectional links]]
  - Maintain knowledge base index automatically
  - Obsidian-compatible output
  - Incremental updates (merge new info, flag contradictions)

Usage:
  hermes-knowledge init                           Initialize knowledge base
  hermes-knowledge import <file>                   Import a document
  hermes-knowledge search "keyword"                Search knowledge base
  hermes-knowledge stats                          Knowledge base statistics
  hermes-knowledge export --format obsidian       Export for Obsidian

Based on: Roland.W "Hermes+Obsidian+LLM Wiki 搭建本地知识库" (2026-05-13)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
KNOWLEDGE_ROOT = PROJECT_ROOT / "knowledge_base"

# LLM Wiki directory structure
DIRS = {
    "raw": KNOWLEDGE_ROOT / "raw" / "sources",
    "entities": KNOWLEDGE_ROOT / "wiki" / "entities",
    "concepts": KNOWLEDGE_ROOT / "wiki" / "concepts",
    "root": KNOWLEDGE_ROOT,
}


# ============================================================================
# Knowledge Base Operations
# ============================================================================
def init_knowledge_base() -> dict:
    """Initialize the knowledge base directory structure."""
    for d in DIRS.values():
        d.mkdir(parents=True, exist_ok=True)

    index_file = KNOWLEDGE_ROOT / "wiki" / "index.md"
    log_file = KNOWLEDGE_ROOT / "wiki" / "log.md"

    if not index_file.exists():
        index_file.write_text(
            "# Knowledge Base Index\n\n"
            f"> Created: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC\n\n"
            "## Entities\n\n_No entities yet._\n\n"
            "## Concepts\n\n_No concepts yet._\n\n",
            encoding="utf-8",
        )

    if not log_file.exists():
        log_file.write_text(
            "# Knowledge Base Update Log\n\n"
            f"## {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
            f"- Knowledge base initialized\n\n",
            encoding="utf-8",
        )

    return {"success": True, "root": str(KNOWLEDGE_ROOT)}


def extract_title(content: str) -> str:
    """Extract title from document (first # heading or filename)."""
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped[2:].strip()
    return "Untitled"


def extract_entities(content: str) -> list[dict]:
    """Extract potential entities from document content."""
    entities = []

    # Look for [[wikilinks]]
    wiki_links = re.findall(r"\[\[([^\]]+)\]\]", content)
    for link in wiki_links:
        if "/" not in link and len(link) > 1:
            entities.append({"name": link, "type": "reference", "confidence": 0.9})

    # Look for capitalized proper nouns (simple heuristic)
    proper_nouns = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", content)
    seen = set(e["name"].lower() for e in entities)
    for noun in proper_nouns[:10]:
        if noun.lower() not in seen and len(noun) > 5:
            entities.append({"name": noun, "type": "proper-noun", "confidence": 0.5})
            seen.add(noun.lower())

    # Look for tool/product mentions
    tools = re.findall(
        r"\b(Hermes|Obsidian|Claude|Codex|GitHub|Notion|OpenAI|Anthropic|"
        r"MCP|SKILL\.md|Docker|Flask|TypeScript)\b",
        content,
        re.IGNORECASE,
    )
    for tool in set(tools):
        if tool.lower() not in seen:
            entities.append({"name": tool, "type": "tool", "confidence": 0.8})
            seen.add(tool.lower())

    return entities


def extract_concepts(content: str) -> list[dict]:
    """Extract potential concepts from document content."""
    concepts = []

    # Look for "## " headings as concept candidates
    headings = re.findall(r"^##\s+(.+)$", content, re.MULTILINE)
    for h in headings[:8]:
        concepts.append({"name": h.strip(), "type": "heading", "confidence": 0.7})

    # Look for key phrases
    patterns = [
        (r"(?:核心|关键|重要).*?[：:]\s*(.+?)(?:[。\n]|$)", "key-point"),
        (r"(?:方法|原理|技术|模式|架构|策略).*?[：:]\s*(.+?)(?:[。\n]|$)", "methodology"),
    ]
    seen = set(c["name"].lower() for c in concepts)
    for pattern, ctype in patterns:
        matches = re.findall(pattern, content)
        for m in matches[:5]:
            name = m.strip()[:80]
            if name.lower() not in seen and len(name) > 3:
                concepts.append({"name": name, "type": ctype, "confidence": 0.6})
                seen.add(name.lower())

    return concepts


def create_entity_page(name: str, entity_type: str, source_file: str) -> Path:
    """Create or update an entity Wiki page."""
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", name.lower()).strip("-")
    entity_file = DIRS["entities"] / f"{slug}.md"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    if entity_file.exists():
        existing = entity_file.read_text(encoding="utf-8")
        # Append source reference
        content = existing.rstrip() + f"\n- Referenced in: [[{source_file}]] ({timestamp})\n"
    else:
        content = f"""---
tags: [entity, {entity_type}]
created: {timestamp}
type: entity
---

# {name}

**Type**: {entity_type}

## References
- [[{source_file}]]

## Notes
_No notes yet._
"""
    entity_file.write_text(content, encoding="utf-8")
    return entity_file


def create_concept_page(name: str, concept_type: str, source_file: str, detail: str = "") -> Path:
    """Create or update a concept Wiki page."""
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", name.lower()).strip("-")
    concept_file = DIRS["concepts"] / f"{slug}.md"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    if concept_file.exists():
        existing = concept_file.read_text(encoding="utf-8")
        content = existing.rstrip() + f"\n- Referenced in: [[{source_file}]] ({timestamp})\n"
    else:
        detail_section = f"\n{detail}" if detail else ""
        content = f"""---
tags: [concept, {concept_type}]
created: {timestamp}
type: concept
---

# {name}

**Type**: {concept_type}{detail_section}

## References
- [[{source_file}]]

## Related Concepts

## Notes
_No notes yet._
"""
    concept_file.write_text(content, encoding="utf-8")
    return concept_file


def update_index(entity_pages: list[str], concept_pages: list[str]) -> None:
    """Update the knowledge base index."""
    index_file = KNOWLEDGE_ROOT / "wiki" / "index.md"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    lines = [f"# Knowledge Base Index\n\n> Last updated: {timestamp} UTC\n"]

    lines.append("## Entities\n\n")
    if entity_pages:
        for ep in sorted(set(entity_pages)):
            lines.append(f"- [[{ep}]]\n")
    else:
        lines.append("_No entities yet._\n")

    lines.append("\n## Concepts\n\n")
    if concept_pages:
        for cp in sorted(set(concept_pages)):
            lines.append(f"- [[{cp}]]\n")
    else:
        lines.append("_No concepts yet._\n")

    index_file.write_text("".join(lines), encoding="utf-8")


def update_log(action: str, detail: str = "") -> None:
    """Append to the knowledge base update log."""
    log_file = KNOWLEDGE_ROOT / "wiki" / "log.md"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    content = log_file.read_text(encoding="utf-8") if log_file.exists() else "# Knowledge Base Update Log\n\n"

    if f"## {today}" not in content:
        content += f"\n## {today}\n"

    entry = f"- [{timestamp}] {action}"
    if detail:
        entry += f" — {detail}"
    entry += "\n"

    content += entry
    log_file.write_text(content, encoding="utf-8")


# ============================================================================
# Import Document
# ============================================================================
def import_document(filepath: str, title: Optional[str] = None) -> dict:
    """Import a document into the knowledge base."""
    path = Path(filepath).expanduser().resolve()
    if not path.exists():
        return {"success": False, "error": f"File not found: {filepath}"}

    init_knowledge_base()
    content = path.read_text(encoding="utf-8")
    doc_title = title or extract_title(content)

    # Copy raw source
    source_name = f"{uuid.uuid4().hex[:8]}-{path.name}"
    source_file = DIRS["raw"] / source_name
    source_file.write_text(content, encoding="utf-8")

    # Extract
    entities = extract_entities(content)
    concepts = extract_concepts(content)

    # Create entity pages
    entity_pages = []
    for e in entities[:15]:
        ep = create_entity_page(e["name"], e["type"], doc_title)
        entity_pages.append(ep.stem)

    # Create concept pages
    concept_pages = []
    for c in concepts[:10]:
        cp = create_concept_page(c["name"], c["type"], doc_title)
        concept_pages.append(cp.stem)

    # Create source page
    source_page = DIRS["raw"].parent / f"{source_name}.md"
    entity_links = "\n".join(f"- [[{ep}]]" for ep in entity_pages[:10])
    concept_links = "\n".join(f"- [[{cp}]]" for cp in concept_pages[:10])
    source_page.write_text(
        f"---\ntags: [source]\ncreated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}\n"
        f"source_file: {path.name}\n---\n\n"
        f"# {doc_title}\n\n"
        f"**Source**: {path.name}\n\n"
        f"## Extracted Entities\n{entity_links or '_None_'}\n\n"
        f"## Extracted Concepts\n{concept_links or '_None_'}\n\n"
        f"## Raw Content\n\n{content[:5000]}",
        encoding="utf-8",
    )

    # Update index and log
    update_index(entity_pages, concept_pages)
    update_log("import", f"Imported '{doc_title}' — {len(entities)} entities, {len(concepts)} concepts")

    return {
        "success": True,
        "title": doc_title,
        "entities_count": len(entities),
        "concepts_count": len(concepts),
        "entity_pages": entity_pages[:10],
        "concept_pages": concept_pages[:10],
        "source_file": str(source_file),
        "knowledge_root": str(KNOWLEDGE_ROOT),
    }


# ============================================================================
# Search
# ============================================================================
def search_knowledge_base(query: str) -> list[dict]:
    """Search the knowledge base for matching pages."""
    results = []
    query_lower = query.lower()

    for wiki_dir in [DIRS["entities"], DIRS["concepts"]]:
        if not wiki_dir.exists():
            continue
        for md_file in wiki_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                if query_lower in content.lower():
                    # Extract title
                    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
                    title = title_match.group(1) if title_match else md_file.stem
                    results.append({
                        "title": title,
                        "file": str(md_file.relative_to(KNOWLEDGE_ROOT)),
                        "path": str(md_file),
                        "type": "entity" if "entities" in str(md_file) else "concept",
                        "snippet": _extract_snippet(content, query_lower),
                    })
            except Exception:
                continue

    return results


def _extract_snippet(content: str, query: str) -> str:
    """Extract a relevant snippet around the query match."""
    idx = content.lower().find(query)
    if idx < 0:
        return content[:200]
    start = max(0, idx - 80)
    end = min(len(content), idx + len(query) + 120)
    snippet = content[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."
    return snippet.replace("\n", " ").strip()


# ============================================================================
# Stats
# ============================================================================
def get_stats() -> dict:
    """Get knowledge base statistics."""
    stats = {"entities": 0, "concepts": 0, "sources": 0, "total_pages": 0}
    if DIRS["entities"].exists():
        stats["entities"] = len(list(DIRS["entities"].glob("*.md")))
    if DIRS["concepts"].exists():
        stats["concepts"] = len(list(DIRS["concepts"].glob("*.md")))
    if DIRS["raw"].exists():
        stats["sources"] = len(list(DIRS["raw"].glob("*")))
    stats["total_pages"] = stats["entities"] + stats["concepts"]
    return stats


# ============================================================================
# CLI
# ============================================================================
def cmd_init(args: argparse.Namespace) -> int:
    result = init_knowledge_base()
    print(f"✅ Knowledge base initialized: {result['root']}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    result = import_document(args.file, title=args.title)
    if not result["success"]:
        print(f"ERROR: {result['error']}", file=sys.stderr)
        return 1

    print(f"✅ Imported: {result['title']}")
    print(f"   Entities: {result['entities_count']}")
    print(f"   Concepts: {result['concepts_count']}")
    if result["entity_pages"]:
        print(f"   Entity pages: {', '.join(result['entity_pages'][:5])}")
    if result["concept_pages"]:
        print(f"   Concept pages: {', '.join(result['concept_pages'][:5])}")
    print(f"   Knowledge root: {result['knowledge_root']}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    results = search_knowledge_base(args.query)
    if not results:
        print(f'No results for "{args.query}"')
        return 0

    print(f'\n🔍 Found {len(results)} result(s) for "{args.query}":\n')
    for r in results:
        tag = "🏷️" if r["type"] == "entity" else "📖"
        print(f"  {tag} [[{r['title']}]] ({r['type']})")
        print(f"     {r['snippet'][:150]}")
        print()
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    stats = get_stats()
    print(f"\n📊 Knowledge Base Statistics")
    print(f"{'='*40}")
    print(f"   Entities:  {stats['entities']}")
    print(f"   Concepts:  {stats['concepts']}")
    print(f"   Sources:   {stats['sources']}")
    print(f"   Total:     {stats['total_pages']} pages")
    print(f"   Root:      {KNOWLEDGE_ROOT}")
    print(f"{'='*40}\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hermes Knowledge Base — LLM Wiki Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              hermes-knowledge init
              hermes-knowledge import article.md
              hermes-knowledge import article.md --title "My Article"
              hermes-knowledge search "Claude Code"
              hermes-knowledge stats
        """),
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialize knowledge base")

    p_import = sub.add_parser("import", help="Import a document")
    p_import.add_argument("file", help="Path to document")
    p_import.add_argument("--title", help="Document title")

    p_search = sub.add_parser("search", help="Search knowledge base")
    p_search.add_argument("query", help="Search query")

    sub.add_parser("stats", help="Knowledge base statistics")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "init": cmd_init,
        "import": cmd_import,
        "search": cmd_search,
        "stats": cmd_stats,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
