# Hermes Workspace 🦞

> 开源 AI 团队工作空间 — 8 个 AI 同事 · 共享记忆 · 安全可审计 · Docker 一键部署。
>
> Moxt.ai 的开源替代品。自托管，按你自己的方式运行。

[![Coworkers](https://img.shields.io/badge/coworkers-8%20active-brightgreen)]()
[![Registry](https://img.shields.io/badge/registry-2%20skills-green)]()
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ready-blue)]()

---

## 🚀 快速开始

```bash
# 一行命令启动
docker compose up -d

# 或本地运行
pip install -r requirements.txt
python3 build/workspace/hermes-dashboard.py
```

打开 http://localhost:5002 — 你的 AI 团队已就绪。

---

## 🏗️ 平台架构

```
┌─────────────────────────────────────────────┐
│                  Phase 4                     │
│  ┌─────────────────────────────────────┐    │
│  │        Plugin Bridge                 │    │
│  │  pre_execution → post → error       │    │
│  │  4 built-in handlers                │    │
│  └─────────────────────────────────────┘    │
│  ┌─────────────────────────────────────┐    │
│  │     Extension Guide (810行)          │    │
│  └─────────────────────────────────────┘    │
├─────────────────────────────────────────────┤
│  Phase 2               Phase 3              │
│  ┌──────────────┐  ┌──────────────────┐    │
│  │ hermes-scan  │  │  hermes-audit    │    │
│  │ A-F 安全评级  │  │  执行收据 JSON    │    │
│  │ 470行 Python  │  │  499行 Python     │    │
│  └──────────────┘  └──────────────────┘    │
├─────────────────────────────────────────────┤
│                  Phase 1                     │
│  ┌─────────────────────────────────────┐    │
│  │        SKILL.md v1 格式规范          │    │
│  │  权限声明 + 成本估算 + 输入输出契约   │    │
│  │  420行规范 + 399行示例技能           │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

---

## 🚀 快速开始

### 扫描一个技能

```bash
pip install pyyaml
python3 build/phase2/hermes-scan.py your-skill.SKILL.md --pretty
```

### 注册表管理

```bash
# 查看已注册技能
python3 build/phase5/hermes-registry.py list

# 搜索技能
python3 build/phase5/hermes-registry.py search backup

# 注册新技能（自动扫描评级）
python3 build/phase5/hermes-registry.py add your-skill.SKILL.md
```

输出示例：
```json
{
  "skill_id": "devops/backup/git-auto-backup",
  "rating": "B",
  "score": 88,
  "findings": [
    {"severity": "warn", "category": "security", "message": "Directory-level wildcard..."}
  ],
  "mandatory_check": {"present": ["skill_id","version","author",...], "missing": []}
}
```

### 审计一次执行

```bash
python3 build/phase3/hermes-audit.py \
  --skill build/phase1/example-skill.SKILL.md \
  --cmd "your-command-here" \
  --output receipt.json
```

### 使用 Plugin Bridge

```python
from hermes_plugin_bridge import PluginBridge
from hermes_plugin_bridge.bridge import create_default_bridge

# 创建带内置安全守卫的桥接
bridge = create_default_bridge()

# 技能执行前检查
decision = bridge.pre_execution(skill_meta, params)
if not decision.allow:
    print(f"已拦截: {decision.reason}")
```

---

## 📋 项目状态

| 阶段 | 内容 | 状态 |
|:----:|------|:----:|
| Phase 1 | SKILL.md v1 格式规范 + 示例技能 | ✅ 完成 |
| Phase 2 | hermes-scan A-F 静态安全分析器 | ✅ 完成 |
| Phase 3 | hermes-audit 执行审计收据 | ✅ 完成 |
| Phase 4 | Extension Guide + Plugin Bridge (3 hooks) | ✅ 完成 |
| Phase 5 | 生态市场 (Skill Registry + Cronalytics 收录) | ✅ 完成 |
| Phase 6 | AI Workspace (8 Coworkers + 共享记忆 + Dashboard) | ✅ 完成 |
| Phase 7 | 内容发行 (Content Skill Template) | 📋 待定 |

---

## 🛣️ 路线图

- **Phase 5** (本周): Skill Registry 注册表 + Plugin Marketplace + Cronalytics 入驻
- **Phase 6** (下周): hermes-scan GitHub Action + MCP Gateway + Shared Memory API
- **Phase 7**: 官方 Content Skill Template + 开发者文档站

---

## 📁 项目结构

```
build/
├── phase1/
│   ├── SKILL.md.v1.spec.md      # 格式规范 (420行)
│   └── example-skill.SKILL.md   # 示例技能 (399行)
├── phase2/
│   ├── hermes-scan.py           # 安全分析器 (470行)
│   └── bad-skill.SKILL.md       # 恶意测试用例
├── phase3/
│   ├── hermes-audit.py          # 审计收据 (499行)
│   └── test-receipt.json        # 测试收据
└── phase4/
    ├── EXTENSION-GUIDE.md       # 开发者指南 (810行)
    └── hermes_plugin_bridge/    # 插件桥接包

registry/
├── skills.json                 # 技能注册表 (2 技能)
└── skills/
    └── cronalytics.SKILL.md    # Cronalytics 收录 (A/91)
```

---

## 🤖 AI 同事

| 角色 | ID | 排程 | Moxt 对标 |
|------|-----|------|:--:|
| 晨报员 | ops/morning-brief | 每日 08:00 | ✅ 独家 |
| 竞品监控员 | ops/competitor-monitor | 每周一 09:00 | ✅ 独家 |
| 社媒运营员 | marketing/social-media | 每日 10:00 | ✅ |
| 冷触达专员 | sales/cold-outreach | 工作日 08:00 | ✅ |
| 合同审查员 | legal/contract-reviewer | 一三五 09:00 | ✅ |
| 线索评估员 | sales/lead-evaluator | 每日 3 次 | ✅ |
| 简历筛选员 | hr/resume-screener | 每日 3 次 | ✅ |
| 多项目追踪员 | ops/project-tracker | 工作日 2 次 | ✅ |

### vs Moxt.ai

| 能力 | Moxt | Hermes Workspace |
|------|:--:|:--:|
| AI 同事 | 8 | **8 + 无限自定义** |
| 共享记忆 | ✅ | ✅ |
| 安全扫描 | ❌ | ✅ A-F 评级 |
| 成本透明 | ❌ | ✅ token 级收据 |
| 开源自部署 | ❌ | ✅ Docker 一键 |
| 定价 | 积分制 | 自带 API key |

- ✅ [Cronalytics](https://github.com/8bit64k/cronalytics) — Hermes cron 可观测性插件，已发起合作讨论 ([Issue #4](https://github.com/8bit64k/cronalytics/issues/4))
- 🟡 [Lanes.sh](https://github.com/lanes-sh/app) — Agent-as-CI 层，Hermes 作为后端执行引擎提案进行中

---

## 📄 许可证

MIT License — 详见 [LICENSE](LICENSE)
