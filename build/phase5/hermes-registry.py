#!/usr/bin/env python3
"""
hermes-registry v2 — Skill Registry CLI + Marketplace API
=========================================================

v2 新增:
  - `install <skill_id>` — 从 GitHub 安装技能到本地
  - `publish <skill_path>` — 发布技能到 Registry + 生成上架 PR
  - `marketplace` — 启动本地 Marketplace API 服务器
  - `stats` — 注册表统计信息
  - `export --format gate-mem` — 导出 GateMem 兼容格式

依赖:
    Python 3.8+, PyYAML, (Flask 用于 marketplace 模式)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import textwrap
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ============================================================================
# Paths
# ============================================================================
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
REGISTRY_FILE = PROJECT_ROOT / "registry" / "skills.json"
HERMES_SCAN_SCRIPT = SCRIPT_DIR.parent / "phase2" / "hermes-scan.py"
SKILLS_DIR = PROJECT_ROOT / "registry" / "skills"

# HTML template for the Marketplace web UI
MARKETPLACE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hermes Skill Marketplace</title>
<style>
  :root { --bg:#0d1117; --bg-card:#161b22; --bg-hover:#1c2333; --border:#30363d; --text:#c9d1d9; --muted:#8b949e; --accent:#3fb950; --blue:#58a6ff; --yellow:#d2991d; --red:#f85149; --purple:#bc8cff; --radius:8px; }
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
  .header{background:var(--bg-card);border-bottom:1px solid var(--border);padding:16px 24px;display:flex;align-items:center;gap:16px;position:sticky;top:0;z-index:10}
  .logo{font-size:24px}
  .header h1{font-size:18px;font-weight:600}
  .header .badge{font-size:11px;background:rgba(63,185,80,.15);color:var(--accent);padding:3px 10px;border-radius:12px;border:1px solid rgba(63,185,80,.3)}
  .container{max-width:1200px;margin:0 auto;padding:20px 24px}
  .search-bar{display:flex;gap:10px;margin-bottom:16px}
  .search-bar input{flex:1;padding:10px 14px;border-radius:var(--radius);border:1px solid var(--border);background:var(--bg-card);color:var(--text);font-size:14px}
  .search-bar input:focus{outline:none;border-color:var(--accent)}
  .stats-row{display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap}
  .stat{background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);padding:12px 16px;font-size:13px}
  .stat .n{font-size:22px;font-weight:700;color:var(--accent)}
  .filters{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
  .chip{padding:4px 12px;border-radius:16px;font-size:12px;cursor:pointer;border:1px solid var(--border);background:var(--bg-card);color:var(--muted);transition:all .15s}
  .chip.active,.chip:hover{background:var(--accent);color:#fff;border-color:var(--accent)}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}
  .card{background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);padding:16px;transition:border-color .15s;display:flex;flex-direction:column;gap:8px}
  .card:hover{border-color:var(--accent)}
  .card-top{display:flex;justify-content:space-between;align-items:flex-start}
  .card-name{font-size:15px;font-weight:600}
  .card-author{font-size:12px;color:var(--muted)}
  .rating{font-size:13px;font-weight:700;padding:2px 8px;border-radius:4px}
  .rating-A{background:rgba(63,185,80,.15);color:var(--accent)}
  .rating-B{background:rgba(210,153,29,.15);color:var(--yellow)}
  .rating-C,.rating-D,.rating-E,.rating-F{background:rgba(139,148,158,.1);color:var(--muted)}
  .card-desc{font-size:12px;color:var(--muted);line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .tags{display:flex;gap:4px;flex-wrap:wrap}
  .tag{padding:1px 6px;border-radius:4px;font-size:10px;background:rgba(88,166,255,.1);color:var(--blue)}
  .card-foot{display:flex;justify-content:space-between;align-items:center;margin-top:auto;padding-top:8px;border-top:1px solid var(--border);font-size:11px;color:var(--muted)}
  .empty{color:var(--muted);text-align:center;padding:60px 20px;font-size:14px}
  .toast{position:fixed;bottom:20px;right:20px;padding:10px 18px;border-radius:var(--radius);background:var(--bg-card);border:1px solid var(--border);font-size:13px;z-index:100;opacity:0;transition:opacity .2s}
  .toast.show{opacity:1}
  @media(max-width:600px){.grid{grid-template-columns:1fr}.header{padding:12px 16px}}
</style>
</head>
<body>
<div class="header">
  <span class="logo">🏪</span>
  <h1>Hermes Skill Marketplace</h1>
  <span class="badge" id="count-badge">8 skills</span>
</div>
<div class="container">
  <div class="search-bar">
    <input type="text" id="search-input" placeholder="Search skills... (name, tag, description)" oninput="renderSkills()">
  </div>
  <div class="stats-row" id="stats-row"></div>
  <div class="filters" id="filters"></div>
  <div class="grid" id="skills-grid"><div class="empty">Loading...</div></div>
</div>
<div class="toast" id="toast"></div>
<script>
var allSkills=[],currentFilter='';
fetch('/skills').then(r=>r.json()).then(d=>{
  allSkills=d.skills||[];
  document.getElementById('count-badge').textContent=d.total+' skills';
  buildStats();
  buildFilters();
  renderSkills();
});
function buildStats(){
  var cats={},rats={};
  allSkills.forEach(s=>{ cats[s.category||'general']=(cats[s.category||'general']||0)+1; rats[s.rating||'?']=(rats[s.rating||'?']||0)+1 });
  var html='<div class="stat"><div class="n">'+allSkills.length+'</div>Total Skills</div>';
  var ratingOrder=['A','B','C','D','E','F'];
  ratingOrder.forEach(r=>{ if(rats[r]) html+='<div class="stat"><div class="n">'+rats[r]+'</div>Rating '+r+'</div>'; });
  document.getElementById('stats-row').innerHTML=html;
}
function buildFilters(){
  var allTags=new Set();
  allSkills.forEach(s=>(s.tags||[]).forEach(t=>allTags.add(t)));
  var cats=new Set();
  allSkills.forEach(s=>cats.add(s.category||'general'));
  var html='<span class="chip active" onclick="setFilter(\'\')">All</span>';
  allTags.forEach(t=>{ html+='<span class="chip" onclick="setFilter(\''+esc(t)+'\')">'+esc(t)+'</span>'; });
  document.getElementById('filters').innerHTML=html;
}
function setFilter(f){ currentFilter=f; document.querySelectorAll('.chip').forEach(c=>c.classList.toggle('active',c.textContent===(f||'All'))); renderSkills(); }
function renderSkills(){
  var q=(document.getElementById('search-input').value||'').toLowerCase();
  var filtered=allSkills.filter(function(s){
    if(currentFilter && !(s.tags||[]).includes(currentFilter)) return false;
    if(!q) return true;
    return [s.skill_id,s.name,s.description,(s.tags||[]).join(' ')].join(' ').toLowerCase().indexOf(q)!==-1;
  });
  var grid=document.getElementById('skills-grid');
  if(!filtered.length){ grid.innerHTML='<div class="empty">No skills match your search</div>'; return; }
  grid.innerHTML=filtered.map(function(s){
    var starHtml=s.stars?' ⭐'+s.stars:'';
    return '<div class="card">'+
      '<div class="card-top">'+
        '<div class="card-name">'+esc(s.name||s.skill_id)+starHtml+'</div>'+
        '<span class="rating rating-'+esc(s.rating||'?')+'">'+esc(s.rating||'?')+'</span>'+
      '</div>'+
      '<div class="card-author">by '+esc(s.author||'unknown')+' · '+esc(s.license||'')+'</div>'+
      '<div class="card-desc">'+esc((s.description||'').substring(0,200))+'</div>'+
      '<div class="tags">'+(s.tags||[]).slice(0,5).map(function(t){return '<span class="tag">'+esc(t)+'</span>';}).join('')+'</div>'+
      '<div class="card-foot">'+
        '<span>'+esc(s.skill_id)+'</span>'+
        '<span>Score: '+(s.score||'?')+'</span>'+
      '</div>'+
    '</div>';
  }).join('');
}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
</script>
</body>
</html>"""


def _load_yaml():
    try:
        import yaml
        return yaml
    except ImportError:
        print("ERROR: PyYAML required. pip install pyyaml", file=sys.stderr)
        sys.exit(2)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def slug_to_name(skill_id: str) -> str:
    last_part = skill_id.rsplit("/", 1)[-1]
    words = re.split(r"[-_.]", last_part)
    return " ".join(w.capitalize() for w in words if w)


# ============================================================================
# Registry I/O
# ============================================================================
def load_registry() -> dict:
    if not REGISTRY_FILE.exists():
        return {"registry_version": "2.0.0", "updated_at": utc_now_iso(), "skills": []}
    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "skills" not in data:
            data["skills"] = []
        return data
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: Cannot parse registry: {exc}", file=sys.stderr)
        return {"registry_version": "2.0.0", "updated_at": utc_now_iso(), "skills": []}


def save_registry(registry: dict) -> None:
    registry["updated_at"] = utc_now_iso()
    registry["total_skills"] = len(registry.get("skills", []))
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False, default=str)
        f.write("\n")


# ============================================================================
# ── NEW: Install skill from GitHub ─────────────────────────────────
# ============================================================================
def cmd_install(args: argparse.Namespace) -> int:
    """Install a skill by ID or GitHub URL."""
    skill_ref = args.skill_ref.strip()

    # If it's a GitHub URL, extract owner/repo
    github_match = re.match(
        r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", skill_ref
    )
    if github_match:
        owner, repo = github_match[0], github_match[1]
    else:
        # Try to find in registry first
        registry = load_registry()
        for skill in registry.get("skills", []):
            if skill.get("skill_id") == skill_ref:
                source = skill.get("source", "")
                gh = re.match(r"https?://github\.com/([^/]+)/([^/]+)", source)
                if gh:
                    owner, repo = gh.group(1), gh.group(2)
                    break
        else:
            print(f"ERROR: Skill '{skill_ref}' not found in registry", file=sys.stderr)
            print("       Use a GitHub URL or register the skill first.", file=sys.stderr)
            return 1

    skill_name = repo.replace(".git", "")
    install_dir = SKILLS_DIR / skill_name
    install_dir.mkdir(parents=True, exist_ok=True)

    print(f"📦 Installing {skill_name}...")
    clone_url = f"https://github.com/{owner}/{repo}.git"

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(install_dir)],
            check=True,
            capture_output=True,
            timeout=60,
        )
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Clone failed: {e.stderr.decode()[:200]}", file=sys.stderr)
        return 1

    # Find SKILL.md in the cloned repo
    skill_files = list(install_dir.rglob("SKILL.md"))
    if skill_files:
        skill_file = skill_files[0]
        print(f"✅ Installed to {install_dir}")
        print(f"   SKILL.md found: {skill_file.relative_to(PROJECT_ROOT)}")
        print(f"   Run: hermes-registry.py add {skill_file.relative_to(PROJECT_ROOT)}")
    else:
        print(f"⚠️  Installed to {install_dir} but no SKILL.md found.")
        print(f"   This repo may not be a Hermes-compatible skill.")

    return 0


# ============================================================================
# ── NEW: Publish to marketplace ────────────────────────────────────
# ============================================================================
def cmd_publish(args: argparse.Namespace) -> int:
    """Publish a skill to the Registry marketplace."""
    skill_path = Path(args.skill_path).expanduser().resolve()

    if not skill_path.exists():
        print(f"ERROR: Skill file not found: {skill_path}", file=sys.stderr)
        return 1

    # Parse frontmatter
    content = skill_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        print("ERROR: No YAML frontmatter found", file=sys.stderr)
        return 1

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        print("ERROR: Unclosed frontmatter", file=sys.stderr)
        return 1

    yaml = _load_yaml()
    fm = yaml.safe_load("\n".join(lines[1:end_idx]))

    skill_id = fm.get("name") or fm.get("skill_id")
    if not skill_id:
        print("ERROR: skill_id/name required in frontmatter", file=sys.stderr)
        return 1

    print(f"📦 Publishing {skill_id}...")
    print(f"   Name: {fm.get('name', skill_id)}")
    print(f"   Version: {fm.get('version', '0.1.0')}")
    print(f"   Author: {fm.get('author', 'unknown')}")
    print(f"   Description: {fm.get('description', '')[:100]}")

    # Run scan
    try:
        proc = subprocess.run(
            [sys.executable, str(HERMES_SCAN_SCRIPT), str(skill_path), "--json"],
            capture_output=True, text=True, timeout=30,
        )
        scan = json.loads(proc.stdout) if proc.returncode == 0 else {}
    except Exception:
        scan = {}

    rating = scan.get("rating", "unscanned")
    score = scan.get("score", 0)
    print(f"   Scan: {rating} ({score}/100)")

    if rating in ("E", "F"):
        print(f"⚠️  Rating {rating} — review recommended before publishing.", file=sys.stderr)

    # Add to registry
    registry = load_registry()
    entry = {
        "skill_id": skill_id,
        "name": fm.get("name", skill_id),
        "version": str(fm.get("version", "0.1.0")),
        "author": str(fm.get("author", "unknown")),
        "description": fm.get("description", "")[:200],
        "rating": rating,
        "score": score,
        "source": f"hermes-registry/{skill_id}",
        "tags": fm.get("tags", []),
        "status": "verified" if rating not in ("E", "F") else "needs_review",
        "category": fm.get("category", "general"),
        "added_at": today_str(),
        "license": fm.get("license", "Unknown"),
    }

    # Update or append
    for i, s in enumerate(registry.get("skills", [])):
        if s.get("skill_id") == skill_id:
            entry["added_at"] = s.get("added_at", entry["added_at"])
            registry["skills"][i] = entry
            print(f"   ♻️  Updated existing entry")
            break
    else:
        registry["skills"].append(entry)
        print(f"   ✅ New entry added")

    save_registry(registry)
    print(f"   Registry saved: {REGISTRY_FILE}")
    print(f"\n✨ Published! View at: http://localhost:5002/api/registry/skills")
    return 0


# ============================================================================
# ── NEW: Marketplace API server ────────────────────────────────────
# ============================================================================
def cmd_marketplace(args: argparse.Namespace) -> int:
    """Start a lightweight Marketplace API server."""
    try:
        from flask import Flask, jsonify, request
    except ImportError:
        print("ERROR: Flask required for marketplace. pip install flask", file=sys.stderr)
        return 1

    app = Flask(__name__)
    port = getattr(args, "port", 5003)

    @app.route("/")
    def index():
        """Serve the Marketplace web UI."""
        return MARKETPLACE_HTML

    @app.route("/api")
    def api_index():
        registry = load_registry()
        return jsonify({
            "name": "Hermes Skill Marketplace",
            "version": "2.0.0",
            "skills_count": len(registry.get("skills", [])),
            "endpoints": [
                "GET /skills — list all skills",
                "GET /skills/<id> — skill detail",
                "GET /search?q=<query> — search",
                "GET /stats — marketplace statistics",
                "GET /health — health check",
            ]
        })

    @app.route("/skills")
    def list_skills():
        registry = load_registry()
        skills = registry.get("skills", [])
        category = request.args.get("category", "")
        min_rating = request.args.get("min_rating", "")
        tag = request.args.get("tag", "")

        filtered = skills
        if category:
            filtered = [s for s in filtered if s.get("category", "") == category]
        if min_rating:
            rating_order = ["A", "B", "C", "D", "E", "F"]
            cutoff = rating_order.index(min_rating) if min_rating in rating_order else 99
            filtered = [s for s in filtered
                       if rating_order.index(s.get("rating", "F")) <= cutoff]
        if tag:
            filtered = [s for s in filtered if tag in s.get("tags", [])]

        return jsonify({
            "success": True,
            "count": len(filtered),
            "total": len(skills),
            "skills": filtered,
        })

    @app.route("/skills/<skill_id>")
    def skill_detail(skill_id):
        registry = load_registry()
        for s in registry.get("skills", []):
            if s.get("skill_id") == skill_id:
                return jsonify({"success": True, "skill": s})
        return jsonify({"success": False, "error": "Not found"}), 404

    @app.route("/search")
    def search():
        q = request.args.get("q", "").lower()
        registry = load_registry()
        results = []
        for s in registry.get("skills", []):
            searchable = " ".join([
                s.get("skill_id", ""), s.get("name", ""),
                s.get("description", ""), " ".join(s.get("tags", []))
            ]).lower()
            if q in searchable:
                results.append(s)
        return jsonify({"success": True, "query": q, "count": len(results), "skills": results})

    @app.route("/stats")
    def stats():
        registry = load_registry()
        skills = registry.get("skills", [])
        ratings = {}
        categories = {}
        for s in skills:
            r = s.get("rating", "?")
            ratings[r] = ratings.get(r, 0) + 1
            c = s.get("category", "general")
            categories[c] = categories.get(c, 0) + 1
        return jsonify({
            "total_skills": len(skills),
            "by_rating": ratings,
            "by_category": categories,
            "avg_score": sum(s.get("score", 0) for s in skills) / max(len(skills), 1),
            "last_updated": registry.get("updated_at", ""),
        })

    @app.route("/health")
    def health():
        return jsonify({"status": "healthy", "service": "Hermes Skill Marketplace"})

    print(f"🏪 Hermes Skill Marketplace API")
    print(f"   URL: http://localhost:{port}")
    print(f"   Docs: http://localhost:{port}/")
    app.run(host="0.0.0.0", port=port, debug=False)


# ============================================================================
# ── NEW: Stats command ─────────────────────────────────────────────
# ============================================================================
def cmd_stats(args: argparse.Namespace) -> int:
    """Display registry statistics."""
    registry = load_registry()
    skills = registry.get("skills", [])

    if not skills:
        print("📭 Registry is empty.")
        return 0

    ratings = {}
    cats = {}
    total_score = 0
    for s in skills:
        r = s.get("rating", "?")
        ratings[r] = ratings.get(r, 0) + 1
        c = s.get("category", "general")
        cats[c] = cats.get(c, 0) + 1
        total_score += s.get("score", 0)

    print(f"\n{'='*60}")
    print(f"📊 Hermes Skill Registry Statistics")
    print(f"{'='*60}")
    print(f"   Total skills:      {len(skills)}")
    print(f"   Average score:     {total_score/max(len(skills),1):.1f}")
    print(f"   Last updated:      {registry.get('updated_at','N/A')[:19]}")
    print(f"\n   By Rating:")
    for r in ["A", "B", "C", "D", "E", "F", "?"]:
        if r in ratings:
            bar = "█" * ratings[r]
            print(f"     {r}: {ratings[r]:>2}  {bar}")
    print(f"\n   By Category:")
    for c, count in sorted(cats.items()):
        print(f"     {c}: {count}")
    print(f"{'='*60}\n")
    return 0


# ============================================================================
# ── GateMem Export ─────────────────────────────────────────────────
# ============================================================================
def cmd_export(args: argparse.Namespace) -> int:
    """Export registry in various formats."""
    fmt = getattr(args, "format", "json")
    registry = load_registry()

    if fmt == "gate-mem":
        # GateMem-compatible export
        output = {
            "format": "gate-mem-v1",
            "exported_at": utc_now_iso(),
            "source": "hermes-skill-registry",
            "skills": [
                {
                    "skill_id": s.get("skill_id"),
                    "rating": s.get("rating"),
                    "score": s.get("score"),
                    "tags": s.get("tags", []),
                    "status": s.get("status"),
                }
                for s in registry.get("skills", [])
            ]
        }
    elif fmt == "csv":
        lines = ["skill_id,rating,score,category,status,tags"]
        for s in registry.get("skills", []):
            lines.append(
                f"{s.get('skill_id','')},{s.get('rating','')},{s.get('score',0)},"
                f"{s.get('category','')},{s.get('status','')},"
                f"\"{' '.join(s.get('tags',[]))}\""
            )
        output = "\n".join(lines)
    else:
        output = registry

    if isinstance(output, dict):
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(output)
    return 0


# ============================================================================
# ── Existing commands (from v1) ────────────────────────────────────
# ============================================================================
def cmd_list(args: argparse.Namespace) -> int:
    registry = load_registry()
    skills = sorted(
        registry.get("skills", []),
        key=lambda s: s.get("score", 0),
        reverse=True,
    )
    if not skills:
        print("📭 Registry is empty.")
        return 0

    print(f"\n{'='*80}")
    print(f"📋 Hermes Skill Registry — {len(skills)} skills")
    print(f"{'='*80}")
    print(f"{'Skill ID':<42} {'Rating':>6} {'Score':>6} {'Category':<14}")
    print(f"{'-'*42} {'-'*6} {'-'*6} {'-'*14}")
    for s in skills:
        sid = s.get("skill_id", "?")
        rating = s.get("rating", "?")
        score = s.get("score", 0)
        cat = s.get("category", "general")
        print(f"{sid[:40]:<42} {rating:>6} {score:>6} {cat:<14}")
    print(f"{'='*80}\n")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    q = args.query.lower()
    registry = load_registry()
    results = []
    for s in registry.get("skills", []):
        searchable = " ".join([
            s.get("skill_id", ""), s.get("name", ""),
            s.get("description", ""), " ".join(s.get("tags", []))
        ]).lower()
        if q in searchable:
            results.append(s)

    if not results:
        print(f'No results for "{args.query}"')
        return 0

    print(f'\n🔍 Found {len(results)} result(s) for "{args.query}":\n')
    for s in results:
        print(f"  [{s.get('rating','?')}/{s.get('score',0)}] {s.get('skill_id')}")
        print(f"       {s.get('description','')[:100]}")
        print(f"       tags: {', '.join(s.get('tags',[]))}")
        print()
    return 0


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hermes Skill Registry — Marketplace CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              hermes-registry.py list
              hermes-registry.py search "memory"
              hermes-registry.py install cronalytics
              hermes-registry.py install https://github.com/user/skill
              hermes-registry.py publish path/to/SKILL.md
              hermes-registry.py marketplace --port 5003
              hermes-registry.py stats
              hermes-registry.py export --format gate-mem
        """),
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List all registered skills")
    p_search = sub.add_parser("search", help="Search skills")
    p_search.add_argument("query", help="Search query")
    p_install = sub.add_parser("install", help="Install skill from GitHub")
    p_install.add_argument("skill_ref", help="Skill ID or GitHub URL")
    p_publish = sub.add_parser("publish", help="Publish skill to marketplace")
    p_publish.add_argument("skill_path", help="Path to SKILL.md file")
    p_market = sub.add_parser("marketplace", help="Start Marketplace API server")
    p_market.add_argument("--port", type=int, default=5003, help="Port (default: 5003)")
    sub.add_parser("stats", help="Registry statistics")
    p_export = sub.add_parser("export", help="Export registry")
    p_export.add_argument("--format", choices=["json", "csv", "gate-mem"], default="json")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "list": cmd_list,
        "search": cmd_search,
        "install": cmd_install,
        "publish": cmd_publish,
        "marketplace": cmd_marketplace,
        "stats": cmd_stats,
        "export": cmd_export,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
