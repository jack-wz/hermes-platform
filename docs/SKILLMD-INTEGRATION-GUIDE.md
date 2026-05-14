# SKILL.md 生态系统集成指南

> 面向第三方工具的 SKILL.md 格式集成文档  
> 适用对象：agent_eval, skillctl, GateMem, 及所有技能基础设施工具

---

## 1. 为什么集成 SKILL.md？

SKILL.md v1 是一个开放、可审计的 AI 技能规范格式。与传统提示词模板不同，SKILL.md 包含：

- **安全元数据** — 权限范围、网络访问、成本估计
- **审计哈希** — 每个版本的可验证签名
- **评分系统** — A-F 安全等级（通过 hermes-scan）
- **执行收据** — 每次运行的 token 消耗、工具调用、完成状态（通过 hermes-audit）

如果你的工具需要操作、分析、或治理 AI 技能，集成 SKILL.md 意味着你可以立即获得这些能力，而不需要自己构建。

## 2. SKILL.md 格式规范

### 最小文件结构

```yaml
---
name: my-skill
version: 1.0.0
description: What this skill does
author: your-name
license: MIT
tags: [ai, automation]
---

# My Skill

Skill body content in Markdown...
```

### 扩展字段（安全 + 审计）

```yaml
---
name: my-skill
version: 1.0.0
description: Does X using Y
author: your-name
license: MIT
tags: [ai, automation]

# Security metadata
security:
  permissions: [file-read, network-outbound]
  max_cost_estimate: 0.05       # USD per run
  network_domains: [api.example.com]
  filesystem_scope: [./data/]
  requires_approval: false

# Execution metadata  
runtime:
  min_tokens: 500
  max_tokens: 8000
  timeout_seconds: 120
  recommended_model: claude-sonnet-4

# Audit metadata
audit:
  hash: sha256:abc123...
  last_scanned: 2026-05-14T14:00:00Z
  scan_rating: A
  scan_score: 91
---
```

## 3. 集成模式

### 3.1 评估工具（agent_eval 类）

```python
# agent_eval 集成示例
import yaml
from pathlib import Path

def evaluate_skill(skill_path: str) -> dict:
    """评估一个 SKILL.md 技能的质量"""
    with open(skill_path) as f:
        content = f.read()
    
    # 解析 YAML frontmatter
    _, frontmatter, body = content.split('---', 2)
    meta = yaml.safe_load(frontmatter)
    
    # 评估维度
    return {
        "skill_id": meta.get("name"),
        "version": meta.get("version"),
        "security_rating": meta.get("security", {}).get("scan_rating", "unscanned"),
        "has_security_metadata": "security" in meta,
        "has_audit_metadata": "audit" in meta,
        "cost_estimate": meta.get("security", {}).get("max_cost_estimate"),
        "permissions_count": len(meta.get("security", {}).get("permissions", [])),
        "body_length": len(body.strip()),
    }
```

### 3.2 治理工具（skillctl 类）

```python
# skillctl 集成示例
def register_skill_to_governance(skill_path: str, registry_path: str):
    """将 SKILL.md 技能注册到治理系统"""
    with open(skill_path) as f:
        content = f.read()
    
    # 提取治理关键字段
    _, fm, _ = content.split('---', 2)
    meta = yaml.safe_load(fm)
    
    governance_record = {
        "skill_id": meta["name"],
        "version": meta["version"],
        "permissions": meta.get("security", {}).get("permissions", []),
        "requires_approval": meta.get("security", {}).get("requires_approval", False),
        "scan_rating": meta.get("audit", {}).get("scan_rating", "unscanned"),
        "registered_at": datetime.utcnow().isoformat(),
    }
    
    # 写入治理注册表
    registry = Path(registry_path)
    existing = json.loads(registry.read_text()) if registry.exists() else []
    existing.append(governance_record)
    registry.write_text(json.dumps(existing, indent=2))
```

### 3.3 基准测试工具（GateMem 类）

```python
# GateMem 兼容导出
# hermes-memory.py v1.2 已内置 gate_mem_compat_export()
from hermes_memory import SharedMemory

mem = SharedMemory()
export = mem.gate_mem_compat_export()

# 输出格式：
# {
#   "format": "gate-mem-v1",
#   "exported_at": "2026-05-14T14:30:00Z",
#   "total_entries": 42,
#   "principals": {
#     "shared": {"principal_type": "team", "entry_count": 15, ...},
#     "personal": {"principal_type": "owner", "entry_count": 8, ...},
#     "board": {"principal_type": "board", "entry_count": 12, ...},
#     "audit": {"principal_type": "governance", "entry_count": 7, ...}
#   }
# }
```

## 4. Hermes Scan 集成

使用 hermes-scan 对 SKILL.md 技能进行安全分析：

```bash
# 扫描单个技能
python3 build/phase2/hermes-scan.py path/to/skill.SKILL.md --json

# 输出示例：
# {
#   "skill_id": "my-skill",
#   "rating": "B",
#   "score": 88,
#   "checks": {
#     "permissions_declared": true,
#     "network_scoped": true,
#     "cost_estimated": true,
#     "audit_hash_present": false,
#     ...
#   }
# }
```

## 5. 获得支持

- **SKILL.md 规范** — `build/phase1/SKILL.md.v1.spec.md`
- **示例技能** — `build/phase1/example-skill.SKILL.md`
- **Hermes Registry** — `registry/skills.json`
- **Plugin Bridge 文档** — `build/phase4/EXTENSION-GUIDE.md`
- **GitHub Issues** — https://github.com/jack-wz/hermes-platform/issues

欢迎提交 Issue 或 PR 将你的工具列入本文档的集成列表。
