#!/usr/bin/env python3
"""Hermes 技能注册表 CLI — 管理 skills.json 的技能索引。"""
import json, sys, os, subprocess
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY_PATH = PROJECT_ROOT / "registry" / "skills.json"
SCAN_PATH = PROJECT_ROOT / "build" / "phase2" / "hermes-scan.py"

def load_registry():
    with open(REGISTRY_PATH) as f:
        return json.load(f)

def save_registry(data):
    data["updated_at"] = datetime.now().isoformat()
    with open(REGISTRY_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def cmd_add(path):
    target = Path(path).resolve()
    if not target.exists():
        print("File not found:", path)
        return

    result = subprocess.run(
        ["python3", str(SCAN_PATH), str(target.resolve())],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("Scan failed:", result.stderr[:200])
        return

    scan = json.loads(result.stdout)
    if scan.get("rating") == "F":
        print("Rating F ({}/100), rejected".format(scan["score"]))
        return

    raw = target.read_text()
    parts = raw.split("---", 2)
    if len(parts) < 3:
        print("No valid frontmatter")
        return

    import yaml
    fm = yaml.safe_load(parts[1])

    author = fm.get("author", {})
    if isinstance(author, dict):
        author_name = author.get("display", author.get("name", "unknown"))
    else:
        author_name = str(author)

    tags = fm.get("tags", []) or []
    if isinstance(fm.get("metadata"), dict):
        htags = fm["metadata"].get("hermes", {}).get("tags", [])
        if htags:
            tags = htags

    entry = {
        "skill_id": scan["skill_id"],
        "name": fm.get("name", scan["skill_id"]),
        "name_zh": fm.get("name_zh", ""),
        "version": fm.get("version", "0.0.0"),
        "author": author_name,
        "description": (fm.get("description", "") or "")[:200],
        "rating": scan["rating"],
        "score": scan["score"],
        "source": "local",
        "path": str(target.relative_to(PROJECT_ROOT)),
        "tags": tags,
        "status": "verified",
        "added_at": datetime.now().isoformat()
    }

    reg = load_registry()
    existing = [i for i, s in enumerate(reg["skills"]) if s["skill_id"] == entry["skill_id"]]
    if existing:
        reg["skills"][existing[0]] = entry
        print("Updated: {} ({}/{})".format(entry["skill_id"], entry["rating"], entry["score"]))
    else:
        reg["skills"].append(entry)
        print("Registered: {} ({}/{})".format(entry["skill_id"], entry["rating"], entry["score"]))

    save_registry(reg)

def cmd_list():
    reg = load_registry()
    skills = reg["skills"]
    if not skills:
        print("(empty)")
        return

    print("Skill Registry ({} skills):\n".format(len(skills)))
    for s in skills:
        tags_str = ", ".join(s.get("tags", [])[:3])
        print("  {:>3s} | {:>3d} | {:<40s} | {}".format(
            s["rating"], s["score"], s["skill_id"], tags_str))

def cmd_search(query):
    reg = load_registry()
    q = query.lower()
    found = []
    for s in reg["skills"]:
        text = "{} {} {} {}".format(
            s["skill_id"], s.get("name", ""), s.get("description", ""),
            " ".join(s.get("tags", []))
        ).lower()
        if q in text:
            found.append(s)

    if not found:
        print('No match for: "{}"'.format(query))
        return

    print('Found {} matches for "{}":\n'.format(len(found), query))
    for s in found:
        print("  {:>3s} | {:>3d} | {:<40s} | {}".format(
            s["rating"], s["score"], s["skill_id"], s.get("author", "?")))

def cmd_show(skill_id):
    reg = load_registry()
    for s in reg["skills"]:
        if s["skill_id"] == skill_id:
            print("Skill ID:    {}".format(s["skill_id"]))
            print("Name:        {}".format(s.get("name", "")))
            print("Version:     {}".format(s.get("version", "")))
            print("Author:      {}".format(s.get("author", "")))
            print("Rating:      {} ({}/100)".format(s.get("rating", ""), s.get("score", 0)))
            print("Source:      {}".format(s.get("source", "")))
            print("Path:        {}".format(s.get("path", "")))
            print("Tags:        {}".format(", ".join(s.get("tags", []))))
            print("Status:      {}".format(s.get("status", "")))
            print("Description: {}".format(s.get("description", "")[:200]))
            return
    print("Skill not found: {}".format(skill_id))

def cmd_scan_all():
    reg = load_registry()
    changes = 0
    for i, s in enumerate(reg["skills"]):
        target = PROJECT_ROOT / s["path"]
        if not target.exists():
            print("Skip {}: file missing".format(s["skill_id"]))
            continue

        result = subprocess.run(
            ["python3", str(SCAN_PATH), str(target)],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            scan = json.loads(result.stdout)
            if scan["rating"] != s["rating"] or scan["score"] != s["score"]:
                print("{}: {}/{} -> {}/{}".format(
                    s["skill_id"], s["rating"], s["score"],
                    scan["rating"], scan["score"]))
                reg["skills"][i]["rating"] = scan["rating"]
                reg["skills"][i]["score"] = scan["score"]
                changes += 1
            else:
                print("OK {}: {}/{} (unchanged)".format(
                    s["skill_id"], scan["rating"], scan["score"]))

    if changes > 0:
        save_registry(reg)
        print("\nUpdated {} skill ratings".format(changes))
    else:
        print("\nAll ratings unchanged")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: hermes-registry.py <add|list|search|show|scan-all> [arg]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "add" and len(sys.argv) > 2:
        cmd_add(sys.argv[2])
    elif cmd == "list":
        cmd_list()
    elif cmd == "search" and len(sys.argv) > 2:
        cmd_search(sys.argv[2])
    elif cmd == "show" and len(sys.argv) > 2:
        cmd_show(sys.argv[2])
    elif cmd == "scan-all":
        cmd_scan_all()
    else:
        print("Unknown command:", cmd)
        print("Usage: hermes-registry.py <add|list|search|show|scan-all> [arg]")
