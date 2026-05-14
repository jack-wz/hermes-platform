#!/usr/bin/env python3
"""
hermes-registry — Skill Registry 命令行工具
============================================

Hermes 技能注册表管理工具。维护 registry/skills.json 索引文件，
支持技能注册、列表、搜索、查看详情、批量重新扫描等操作。

用法:
    hermes-registry.py add <skill_path>       # 扫描并注册新技能
    hermes-registry.py list                    # 列出所有已注册技能（含评级）
    hermes-registry.py search <query>          # 按名称/标签/描述搜索
    hermes-registry.py show <skill_id>         # 查看单个技能完整信息
    hermes-registry.py scan-all                # 重新扫描所有已注册技能并更新评级

依赖:
    - Python 3.8+
    - PyYAML (pip install pyyaml)
    - hermes-scan.py（Phase 2，位于 ../phase2/hermes-scan.py）
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ============================================================================
# 路径解析
# ============================================================================

# 脚本所在目录：build/phase5/
SCRIPT_DIR = Path(__file__).resolve().parent

# 项目根目录：../../ (相对于 build/phase5/)
PROJECT_ROOT = SCRIPT_DIR.parent.parent

# 注册表文件路径：registry/skills.json（项目根目录下）
REGISTRY_FILE = PROJECT_ROOT / "registry" / "skills.json"

# hermes-scan.py 路径：build/phase2/hermes-scan.py
HERMES_SCAN_SCRIPT = SCRIPT_DIR.parent / "phase2" / "hermes-scan.py"


# ============================================================================
# 工具函数
# ============================================================================

def _load_yaml():
    """懒加载 PyYAML，未安装时给出友好提示。"""
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
    """返回当前 UTC 时间的 ISO-8601 字符串（带 Z 后缀）。"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def today_str() -> str:
    """返回当前日期字符串 YYYY-MM-DD。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def slug_to_name(skill_id: str) -> str:
    """从 skill_id 的最后一段推导人类可读名称。

    例如: 'devops/backup/git-auto-backup' → 'Git Auto Backup'
    """
    last_part = skill_id.rsplit("/", 1)[-1]  # 取最后一段
    # 将连字符和点号替换为空格，每个词首字母大写
    words = re.split(r"[-_.]", last_part)
    return " ".join(w.capitalize() for w in words if w)


# ============================================================================
# 注册表文件读写
# ============================================================================

def load_registry() -> dict:
    """加载 registry/skills.json，若文件不存在则返回空注册表。

    Returns:
        dict: 注册表对象，格式: {"registry_version": "...", "updated_at": "...", "skills": [...]}
    """
    if not REGISTRY_FILE.exists():
        return {
            "registry_version": "1.0.0",
            "updated_at": utc_now_iso(),
            "skills": [],
        }
    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 兼容旧格式：确保 skills 字段存在
        if "skills" not in data:
            data["skills"] = []
        return data
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: Cannot parse registry file: {exc}", file=sys.stderr)
        print("       Starting with an empty registry.", file=sys.stderr)
        return {
            "registry_version": "1.0.0",
            "updated_at": utc_now_iso(),
            "skills": [],
        }


def save_registry(registry: dict) -> None:
    """保存注册表到 registry/skills.json。

    自动更新 updated_at 时间戳，确保目录存在。
    """
    registry["updated_at"] = utc_now_iso()
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False, default=str)
        f.write("\n")


def find_skill_index(registry: dict, skill_id: str) -> Optional[int]:
    """在注册表中查找技能索引，未找到返回 None。"""
    for i, skill in enumerate(registry.get("skills", [])):
        if skill.get("skill_id") == skill_id:
            return i
    return None


# ============================================================================
# SKILL.md 前端元数据解析
# ============================================================================

def parse_skill_frontmatter(filepath: str) -> dict:
    """解析 SKILL.md 文件的 YAML frontmatter。

    返回 dict 包含:
        - ok (bool): 解析是否成功
        - fm (dict|None): 解析出的 frontmatter 字典
        - error (str|None): 错误信息（若失败）
    """
    result: dict = {"ok": False, "fm": None, "error": None}

    try:
        content = Path(filepath).read_text(encoding="utf-8")
    except FileNotFoundError:
        result["error"] = f"File not found: {filepath}"
        return result
    except Exception as exc:
        result["error"] = f"Cannot read file: {exc}"
        return result

    lines = content.split("\n")

    # 检查 frontmatter 起始分隔符 ---
    if not lines or lines[0].strip() != "---":
        result["error"] = "No YAML frontmatter found (file must start with ---)"
        return result

    # 查找结束分隔符 ---
    end_idx: Optional[int] = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        result["error"] = "Unclosed frontmatter: missing closing ---"
        return result

    # 提取 YAML 文本
    frontmatter_text = "\n".join(lines[1:end_idx])

    yaml = _load_yaml()
    try:
        fm = yaml.safe_load(frontmatter_text)
    except Exception as exc:
        result["error"] = f"YAML parse error: {exc}"
        return result

    if fm is None or not isinstance(fm, dict):
        result["error"] = "Empty or invalid frontmatter"
        return result

    result["ok"] = True
    result["fm"] = fm
    return result


# ============================================================================
# hermes-scan 集成
# ============================================================================

def run_scan(skill_path: str) -> dict:
    """调用 hermes-scan.py 扫描技能，返回 JSON 报告。

    寻找策略（与 hermes-audit.py 一致）：
    1. 优先查找 build/phase2/hermes-scan.py（相对于脚本目录）
    2. 然后查找脚本同级目录下的 hermes-scan.py

    Returns:
        dict: 扫描报告，包含 skill_id, rating, score 等字段。
              若扫描失败，返回 rating='F', score=0。
    """
    scan_script = HERMES_SCAN_SCRIPT
    if not scan_script.exists():
        # 备选：脚本同级目录
        scan_script = SCRIPT_DIR / "hermes-scan.py"

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
            "error": "hermes-scan produced invalid JSON",
        }
    except Exception as exc:
        return {
            "skill_id": None,
            "rating": "F",
            "score": 0,
            "error": f"hermes-scan failed: {exc}",
        }


def extract_author_name(author: Any) -> str:
    """从 author 字段提取人类可读的作者名称。

    支持:
    - 字符串: 'team_build' → 'team_build'
    - 对象 dict: {name: 'team_build'} → 'team_build'
     或 {name: 'team_build', display: '技术开发·工匠长'} → '技术开发·工匠长'
    - author.name 不存在时回退到 str(author)
    """
    if isinstance(author, dict):
        # 优先使用 display 名称，其次 name
        display = author.get("display")
        if display:
            return str(display)
        name = author.get("name")
        if name:
            return str(name)
        return str(author)
    if isinstance(author, str):
        return author.strip()
    return str(author) if author is not None else "unknown"


def extract_tags(fm: dict) -> list[str]:
    """从 frontmatter 中提取标签列表。

    查找顺序: fm.tags → fm.metadata.hermes.tags
    """
    # 顶层 tags
    tags = fm.get("tags", [])
    if isinstance(tags, list) and len(tags) > 0:
        return [str(t) for t in tags]

    # metadata.hermes.tags（向后兼容旧格式）
    meta = fm.get("metadata", {})
    if isinstance(meta, dict):
        hermes = meta.get("hermes", {})
        if isinstance(hermes, dict):
            h_tags = hermes.get("tags", [])
            if isinstance(h_tags, list) and len(h_tags) > 0:
                return [str(t) for t in h_tags]

    return []


def build_skill_entry(
    skill_path: str,
    fm: dict,
    scan_report: dict,
    source: str = "hermes-platform",
) -> dict:
    """根据扫描结果和 frontmatter 构建注册表技能条目。

    Args:
        skill_path: 技能文件路径（相对于项目根目录）
        fm: 解析后的 YAML frontmatter 字典
        scan_report: hermes-scan 返回的 JSON 报告
        source: 技能来源标识

    Returns:
        dict: 符合 registry/skills.json 格式的技能条目
    """
    skill_id = scan_report.get("skill_id") or fm.get("skill_id", "unknown")

    # 名称推导：优先从 skill_id 最后一段自动生成
    name = slug_to_name(skill_id)

    # 版本
    version = str(fm.get("version", "0.0.0"))

    # 作者
    author = extract_author_name(fm.get("author", "unknown"))

    # 描述（中文）
    desc = fm.get("description", "")
    if isinstance(desc, str):
        # 合并多行描述为单行（去除换行）
        description_zh = " ".join(desc.split())
        # 限制长度
        if len(description_zh) > 200:
            description_zh = description_zh[:197] + "..."
    else:
        description_zh = str(desc)

    # 标签
    tags = extract_tags(fm)

    return {
        "skill_id": skill_id,
        "name": name,
        "version": version,
        "author": author,
        "description_zh": description_zh,
        "rating": scan_report.get("rating", "F"),
        "score": scan_report.get("score", 0),
        "source": source,
        "path": skill_path,
        "tags": tags,
        "status": "verified" if scan_report.get("rating", "F") not in ("E", "F") else "needs_review",
        "added_at": today_str(),
    }


# ============================================================================
# 命令实现
# ============================================================================

def cmd_add(args: argparse.Namespace) -> int:
    """注册一个新技能到注册表。

    流程:
    1. 解析技能 path → 解析 frontmatter
    2. 调用 hermes-scan 扫描评分
    3. 构建条目并写入注册表
    4. 若 skill_id 已存在，更新已有条目
    """
    # --- 解析技能路径 ---
    skill_path = Path(args.skill_path).expanduser()
    if not skill_path.is_absolute():
        # 相对于当前工作目录
        skill_path = Path.cwd() / skill_path
    skill_path = skill_path.resolve()

    if not skill_path.exists():
        print(f"ERROR: Skill file not found: {skill_path}", file=sys.stderr)
        return 1

    # 尝试计算相对于项目根目录的路径
    try:
        rel_path = str(skill_path.relative_to(PROJECT_ROOT))
    except ValueError:
        rel_path = str(skill_path)

    print(f"📄 正在分析技能: {rel_path}")

    # --- 解析 frontmatter ---
    parsed = parse_skill_frontmatter(str(skill_path))
    if not parsed["ok"]:
        print(f"ERROR: {parsed['error']}", file=sys.stderr)
        return 1
    fm = parsed["fm"]

    skill_id = fm.get("skill_id")
    if not skill_id:
        print("ERROR: skill_id not found in frontmatter", file=sys.stderr)
        return 1

    # --- 调用 hermes-scan ---
    print(f"🔍 正在扫描: {skill_id}")
    scan_report = run_scan(str(skill_path))

    if "error" in scan_report and scan_report.get("rating") == "F":
        print(f"⚠️  扫描警告: {scan_report['error']}", file=sys.stderr)

    rating = scan_report.get("rating", "F")
    score = scan_report.get("score", 0)
    print(f"   评级: {rating} ({score}/100)")

    # --- 构建条目 ---
    source = getattr(args, "source", "hermes-platform") or "hermes-platform"
    entry = build_skill_entry(rel_path, fm, scan_report, source=source)

    # --- 写入注册表 ---
    registry = load_registry()
    existing_idx = find_skill_index(registry, skill_id)

    if existing_idx is not None:
        # 更新已有条目（保留原始 added_at）
        old_entry = registry["skills"][existing_idx]
        entry["added_at"] = old_entry.get("added_at", entry["added_at"])
        registry["skills"][existing_idx] = entry
        action = "已更新"
        print(f"♻️  {action} 技能: {skill_id}")
    else:
        registry["skills"].append(entry)
        action = "已注册"
        print(f"✅ {action} 技能: {skill_id}")

    save_registry(registry)
    print(f"   注册表已保存: {REGISTRY_FILE}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """列出所有已注册技能，按评级排序。

    输出格式: 表格显示 skill_id / name / rating / score / status
    """
    registry = load_registry()
    skills = registry.get("skills", [])

    if not skills:
        print("📭 注册表为空。使用 'hermes-registry.py add <path>' 注册第一个技能。")
        return 0

    # 按评分降序排序
    skills_sorted = sorted(skills, key=lambda s: s.get("score", 0), reverse=True)

    # 打印表头
    print(f"\n{'=' * 80}")
    print(f"📋 Hermes Skill Registry — {len(skills_sorted)} 个技能")
    print(f"{'=' * 80}")
    print(f"{'Skill ID':<42} {'Rating':>6} {'Score':>6} {'Status':<14}")
    print(f"{'-' * 42} {'-' * 6} {'-' * 6} {'-' * 14}")

    for s in skills_sorted:
        sid = s.get("skill_id", "?")
        rating = s.get("rating", "?")
        score = s.get("score", 0)
        status = s.get("status", "?")
        # 截断过长的 skill_id
        display_id = sid if len(sid) <= 40 else sid[:37] + "..."
        print(f"{display_id:<42} {rating:>6} {score:>6} {status:<14}")

    print(f"{'=' * 80}\n")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    """搜索已注册技能。

    搜索范围: skill_id, name, description_zh, tags
    大小写不敏感。
    """
    query = args.query.lower()
    registry = load_registry()
    skills = registry.get("skills", [])

    results = []
    for s in skills:
        # 构建搜索文本
        searchable = " ".join([
            s.get("skill_id", ""),
            s.get("name", ""),
            s.get("description_zh", ""),
            " ".join(s.get("tags", [])),
        ]).lower()

        if query in searchable:
            results.append(s)

    if not results:
        print(f"🔍 未找到匹配 '{args.query}' 的技能。")
        return 0

    print(f"\n🔍 搜索 '{args.query}' — 找到 {len(results)} 个结果:\n")

    for s in results:
        sid = s.get("skill_id", "?")
        name = s.get("name", "?")
        rating = s.get("rating", "?")
        score = s.get("score", 0)
        desc = s.get("description_zh", "")
        tags = ", ".join(s.get("tags", []))

        print(f"  📦 {name}")
        print(f"     ID:      {sid}")
        print(f"     评级:    {rating} ({score}/100)")
        print(f"     描述:    {desc}")
        if tags:
            print(f"     标签:    {tags}")
        print()

    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """显示单个技能的完整注册信息。"""
    skill_id = args.skill_id
    registry = load_registry()

    idx = find_skill_index(registry, skill_id)
    if idx is None:
        print(f"ERROR: Skill not found: {skill_id}", file=sys.stderr)
        # 尝试模糊搜索
        print(f"\n💡 尝试搜索类似技能:", file=sys.stderr)
        for s in registry.get("skills", []):
            if skill_id.lower() in s.get("skill_id", "").lower():
                print(f"   - {s.get('skill_id')}", file=sys.stderr)
        return 1

    skill = registry["skills"][idx]

    # 格式化输出
    print(f"\n{'=' * 60}")
    print(f"📦 {skill.get('name', '?')}")
    print(f"{'=' * 60}")
    print(f"  Skill ID:     {skill.get('skill_id', '?')}")
    print(f"  Version:      {skill.get('version', '?')}")
    print(f"  Author:       {skill.get('author', '?')}")
    print(f"  Rating:       {skill.get('rating', '?')} ({skill.get('score', 0)}/100)")
    print(f"  Status:       {skill.get('status', '?')}")
    print(f"  Source:       {skill.get('source', '?')}")
    print(f"  Path:         {skill.get('path', '?')}")
    print(f"  Added:        {skill.get('added_at', '?')}")
    print(f"  Tags:         {', '.join(skill.get('tags', []))}")
    print(f"  Description:  {skill.get('description_zh', '')}")
    print(f"{'=' * 60}\n")

    return 0


def cmd_scan_all(args: argparse.Namespace) -> int:
    """重新扫描所有已注册技能，更新评分和状态。

    保留所有元数据不变，仅更新:
    - rating / score（来自 hermes-scan）
    - status（根据新评级自动调整）
    - version / tags / description_zh（从 frontmatter 重新提取）
    """
    registry = load_registry()
    skills = registry.get("skills", [])

    if not skills:
        print("📭 注册表为空，无需扫描。")
        return 0

    print(f"🔍 正在重新扫描 {len(skills)} 个技能...\n")

    updated_count = 0
    error_count = 0

    for i, skill in enumerate(skills):
        skill_id = skill.get("skill_id", "?")
        skill_path = skill.get("path", "")

        # 构建绝对路径
        abs_path = PROJECT_ROOT / skill_path
        if not abs_path.exists():
            # 尝试用原始 path 直接查找
            abs_path = Path(skill_path)
            if not abs_path.is_absolute():
                abs_path = PROJECT_ROOT / skill_path

        if not abs_path.exists():
            print(f"⚠️  [{i+1}/{len(skills)}] {skill_id} — 文件不存在: {skill_path}")
            error_count += 1
            continue

        # 重新扫描
        scan_report = run_scan(str(abs_path))

        old_rating = skill.get("rating", "?")
        old_score = skill.get("score", 0)
        new_rating = scan_report.get("rating", "F")
        new_score = scan_report.get("score", 0)

        if new_rating != old_rating or new_score != old_score:
            change = f"{old_rating}→{new_rating}" if new_rating != old_rating else f"score {old_score}→{new_score}"
            status = "🔄"
        else:
            change = "无变化"
            status = "✅"

        # 更新评分
        skill["rating"] = new_rating
        skill["score"] = new_score
        skill["status"] = "verified" if new_rating not in ("E", "F") else "needs_review"

        # 尝试重新解析 frontmatter 以获取最新元数据
        try:
            parsed = parse_skill_frontmatter(str(abs_path))
            if parsed["ok"]:
                fm = parsed["fm"]
                skill["version"] = str(fm.get("version", skill.get("version", "0.0.0")))
                skill["tags"] = extract_tags(fm)
                desc = fm.get("description", "")
                if isinstance(desc, str):
                    desc = " ".join(desc.split())
                    if len(desc) > 200:
                        desc = desc[:197] + "..."
                skill["description_zh"] = desc or skill.get("description_zh", "")
                author = extract_author_name(fm.get("author"))
                if author and author != "unknown":
                    skill["author"] = author
        except Exception:
            pass  # 元数据更新失败不影响评分更新

        print(f"  {status} [{i+1}/{len(skills)}] {skill_id:<45} {new_rating} ({new_score}/100)  {change}")
        updated_count += 1

    # 保存
    save_registry(registry)
    print(f"\n✅ 扫描完成: {updated_count} 个技能已更新, {error_count} 个错误")
    print(f"   注册表已保存: {REGISTRY_FILE}")
    return 0 if error_count == 0 else 1


# ============================================================================
# CLI 入口
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="hermes-registry",
        description=(
            "Hermes Skill Registry — 技能注册表管理工具\n"
            "管理 registry/skills.json 索引，支持注册、列表、搜索、详情、批量扫描。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            使用示例:
              hermes-registry.py add build/phase1/example-skill.SKILL.md
              hermes-registry.py list
              hermes-registry.py search backup
              hermes-registry.py show devops/backup/git-auto-backup
              hermes-registry.py scan-all
        """),
    )

    subparsers = parser.add_subparsers(
        dest="command",
        title="可用命令",
        description="选择一个命令来管理技能注册表。",
    )
    subparsers.required = True

    # ---- add ----
    parser_add = subparsers.add_parser(
        "add",
        help="注册新技能到注册表",
        description="扫描指定的 SKILL.md 文件并将其加入技能注册表。若 skill_id 已存在则更新。",
    )
    parser_add.add_argument(
        "skill_path",
        help="SKILL.md 技能文件的路径（绝对路径或相对路径）",
    )
    parser_add.add_argument(
        "--source",
        default="hermes-platform",
        help="技能来源标识（默认: hermes-platform）",
    )
    parser_add.set_defaults(func=cmd_add)

    # ---- list ----
    parser_list = subparsers.add_parser(
        "list",
        help="列出所有已注册技能",
        description="显示注册表中所有技能，按评分降序排列。",
    )
    parser_list.set_defaults(func=cmd_list)

    # ---- search ----
    parser_search = subparsers.add_parser(
        "search",
        help="搜索技能",
        description="按名称、标签、描述关键词搜索注册表中的技能。大小写不敏感。",
    )
    parser_search.add_argument(
        "query",
        help="搜索关键词",
    )
    parser_search.set_defaults(func=cmd_search)

    # ---- show ----
    parser_show = subparsers.add_parser(
        "show",
        help="查看技能详细信息",
        description="显示指定 skill_id 的完整注册信息。",
    )
    parser_show.add_argument(
        "skill_id",
        help="技能的 skill_id（如 devops/backup/git-auto-backup）",
    )
    parser_show.set_defaults(func=cmd_show)

    # ---- scan-all ----
    parser_scan = subparsers.add_parser(
        "scan-all",
        help="重新扫描所有已注册技能",
        description="对所有已注册技能重新运行 hermes-scan，更新评级和状态。",
    )
    parser_scan.set_defaults(func=cmd_scan_all)

    return parser


def main() -> None:
    """主入口：解析参数并分派到对应命令处理函数。"""
    parser = build_parser()
    args = parser.parse_args()

    # 切换到项目根目录，确保相对路径解析正确
    os.chdir(PROJECT_ROOT)

    try:
        exit_code = args.func(args)
        sys.exit(exit_code if exit_code is not None else 0)
    except KeyboardInterrupt:
        print("\n⏹️  操作已取消。", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f"\n💥 意外错误: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
