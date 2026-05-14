# Hermes Workspace 🦞

> **开源 AI 团队工作空间** — 8 个 AI 同事 · 共享记忆 · 安全可审计 · Docker 一键部署  
> *Moxt.ai 的开源替代品。自托管，按你自己的方式运行。*

[![Tests](https://img.shields.io/badge/tests-17%20passed-brightgreen)](tests/)
[![CI/CD](https://img.shields.io/badge/CI-CD%20pipeline-blue)](.github/workflows/ci.yml)
[![Registry](https://img.shields.io/badge/registry-7%20skills-green)](registry/skills.json)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ready-blue)](Dockerfile)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)

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
┌─────────────────────────────────────────────────────────────┐
│                    Hermes Workspace                          │
├─────────────────────────────────────────────────────────────┤
│  Web Dashboard  │  REST API  │  CLI Tools  │  Docker Deploy │
├─────────────────────────────────────────────────────────────┤
│  🤖 AI Coworkers          │  🧠 Shared Memory (v1.2)        │
│  8 预构建同事              │  命名空间隔离 · GateMem 审计     │
│  Coworker Engine CLI       │  "纠正一次，全员记住"            │
├─────────────────────────────────────────────────────────────┤
│  📋 Skill Registry (v2)   │  🔌 Plugin Bridge               │
│  Marketplace API           │  3 Hooks + 4 Handlers           │
│  install/publish/search    │  TypeScript + Python SDK        │
├─────────────────────────────────────────────────────────────┤
│  🔍 hermes-scan            │  📊 hermes-audit                │
│  A-F 安全分析器             │  执行收据 · Token 估算          │
│  权限/成本/网络/文件系统     │  签名验证 · 审计日志            │
├─────────────────────────────────────────────────────────────┤
│  📄 SKILL.md v1            │  📚 Extension Guide             │
│  开放技能格式规范            │  4 阶段接入流程                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 🦞 vs 竞品

| 维度 | **Hermes** | Moxt.ai | Claude for SB | iFlytek SkillHub | SkillDock |
|------|:----------:|:-------:|:-------------:|:----------------:|:---------:|
| **类型** | **工作空间 + 运行时** | SaaS 工作空间 | SaaS 平台 | 纯 Registry | 桌面管理器 |
| **模型** | ✅ 任意模型 | 单一（积分） | Claude only | N/A | N/A |
| **部署** | ✅ 自托管 Docker | SaaS 闭源 | SaaS | Java/PostgreSQL/Redis/S3 | Electron 桌面 |
| **技能格式** | ✅ 开放 SKILL.md | 自定义闭源 | Anthropic 专用 | SKILL.md | 多格式 |
| **安全扫描** | ✅ A-F 评级 | ❌ | 预审（闭源） | 人工审核 | ❌ |
| **审计** | ✅ Token级收据 | ❌ 黑箱 | ❌ | 操作审计 | ❌ |
| **共享记忆** | ✅ 命名空间+GateMem | ❌ | ❌ | ❌ | ❌ |
| **AI 同事** | ✅ 8 预构建 | ❌ | 8 工作流（闭源） | ❌ | ❌ |
| **插件生态** | ✅ Plugin Bridge | ❌ | ❌ | ❌ | ✅ 15+ 工具同步 |
| **开源** | ✅ MIT | ❌ | ❌ | ✅ 开源 | ✅ 开源 |

---

## 📦 8 个 AI 同事

| 同事 | 部门 | 职责 |
|------|:----:|------|
| ☀️ **Morning Brief** | Ops | 每日晨报：信号+风险+行动建议 |
| 🔍 **Competitor Monitor** | Ops | 竞品监控：GitHub+官网+新闻 |
| 📊 **Project Tracker** | Ops | 项目追踪：进度+阻塞+里程碑 |
| 💼 **Cold Outreach** | Sales | 冷触达：线索评估+第一封 DM |
| 🎯 **Lead Evaluator** | Sales | 线索评分：信号质量+预算估算 |
| 📣 **Social Media** | Marketing | 社媒运营：内容排期+发布 |
| ⚖️ **Contract Reviewer** | Legal | 合同审查：条款+风险+建议 |
| 👥 **Resume Screener** | HR | 简历筛选：匹配度+关键指标 |

---

## 🛡️ 安全扫描

```bash
# 扫描技能安全等级
python3 build/phase2/hermes-scan.py path/to/skill.SKILL.md --json
# → {"rating": "A", "score": 91, "checks": {...}}
```

6 维度检查：权限声明 · 网络范围 · 成本估算 · 文件系统范围 · 审计哈希 · 依赖安全

---

## 📊 审计收据

```bash
# 生成执行审计收据
python3 build/phase3/hermes-audit.py --skill path/to/skill.SKILL.md --run-id abc123
# → {"receipt_id": "...", "token_estimate": 1500, "tools_called": [...], ...}
```

---

## 🏪 技能市场

```bash
# CLI
python3 build/phase5/hermes-registry.py list
python3 build/phase5/hermes-registry.py search "memory"
python3 build/phase5/hermes-registry.py install cronalytics
python3 build/phase5/hermes-registry.py publish path/to/SKILL.md

# Marketplace API
python3 build/phase5/hermes-registry.py marketplace --port 5003
# → http://localhost:5003/skills
```

---

## 🧠 共享记忆 v1.2

```bash
# 添加记忆（纠正一次，全员记住）
python3 build/workspace/hermes-memory.py add "竞品监控需包含 GitHub trending" --author "human:CEO"

# 命名空间管理（v1.2 新增）
python3 build/workspace/hermes-memory.py namespaces
# → shared | personal | board | audit

# GateMem 审计导出
python3 build/workspace/hermes-memory.py gate-mem-export
```

---

## 🔌 插件生态

| 技能 | 评级 | 作者 | 来源 |
|------|:----:|------|------|
| **Cronalytics** | A/91 | Cronalytics | [GitHub](https://github.com/cronalytics) |
| **OpenClaw-Hawkins** | A/85 | parijatmukherjee | [GitHub](https://github.com/parijatmukherjee/openclaw-hawkins) |
| **GateMem** | B/72 | rzhub | [GitHub](https://github.com/rzhub/GateMem) |

---

## 📂 项目结构

```
hermes-platform/
├── build/
│   ├── phase1/         SKILL.md v1 格式规范 + 示例
│   ├── phase2/         hermes-scan 安全分析器
│   ├── phase3/         hermes-audit 审计收据系统
│   ├── phase4/         Extension Guide + Plugin Bridge
│   ├── phase5/         Skill Registry + Marketplace API (v2)
│   └── workspace/      Dashboard + Coworker Engine + Memory
├── registry/
│   ├── skills.json     技能索引
│   ├── skills/         已安装技能
│   └── coworkers/      8 个 AI 同事定义
├── docs/               竞品分析 · 内容定位 · 集成指南
├── tests/              17 单元测试 + 10 集成测试
├── .github/workflows/  CI/CD 流水线
├── Dockerfile          多阶段构建 · 非 root · 健康检查
└── docker-compose.yml  一键部署
```

---

## 📖 文档

- [竞品格局与差异化](docs/COMPETITIVE-LANDSCAPE.md) — iFlytek(3331★) × SkillDock(51★) × skills-manager(1415★)
- [Multi-Model 为何胜出](docs/WHY-MULTI-MODEL-WINS.md) — Claude for SB 对标
- [Agent 记忆不是 Vector DB](docs/AGENT-MEMORY-NOT-VECTOR-DB.md) — 品类爆发分析
- [Claude Code /goal 评估](docs/CLAUDE-CODE-GOAL-ASSESSMENT.md) — 技术差异
- [SKILL.md 集成指南](docs/SKILLMD-INTEGRATION-GUIDE.md) — agent_eval/skillctl/GateMem

---

## 🚢 Docker 部署

```bash
docker build -t hermes-workspace .
docker run -d -p 5002:5002 --name hermes hermes-workspace
# 健康检查: docker inspect --format='{{.State.Health.Status}}' hermes
```

---

**MIT License** · [GitHub](https://github.com/jack-wz/hermes-platform) · Issues welcome
