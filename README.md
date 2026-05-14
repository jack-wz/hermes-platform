# Hermes 平台 🦞

> AI Agent 技能生命周期管理平台 — 让每个技能都可审计、可信任、可组合。

[![Phase](https://img.shields.io/badge/phase-4%2F4%20complete-brightgreen)](https://github.com/jack-wz/hermes-platform)
[![Build](https://img.shields.io/badge/build-verified-brightgreen)]()
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

---

## 这是什么？

Hermes 平台是一套 **AI Agent 技能的标准格式 + 安全扫描 + 审计追踪 + 插件扩展** 系统。它为 AI Agent 生态解决三个核心问题：

1. **技能格式混乱** — 每个 agent 的 skill 格式不同，无法互操作
2. **安全不可见** — 技能能访问什么、花多少钱，调用者不知道
3. **执行无追溯** — 技能跑了没有、花了多少 token、结果如何，没有统一记录

Hermes 平台的答案是：**SKILL.md v1 格式规范 + hermes-scan 安全评级 + hermes-audit 执行收据 + Plugin Bridge 扩展系统**。

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
# 安装依赖
pip install pyyaml

# 扫描技能文件，输出 A-F 评级
python3 build/phase2/hermes-scan.py your-skill.SKILL.md --pretty
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
| Phase 5 | 生态市场 (Skill Registry + Plugin Marketplace) | 🔜 规划中 |
| Phase 6 | 开发者平台 (CI/CD + MCP Gateway) | 📋 待定 |
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
    ├── hermes-plugin-bridge.py  # 插件桥接 (577行)
    └── plugin-config.example.json
```

---

## 🤝 生态接触

- ✅ [Cronalytics](https://github.com/8bit64k/cronalytics) — Hermes cron 可观测性插件，已发起合作讨论 ([Issue #4](https://github.com/8bit64k/cronalytics/issues/4))
- 🟡 [Lanes.sh](https://github.com/lanes-sh/app) — Agent-as-CI 层，Hermes 作为后端执行引擎提案进行中

---

## 📄 许可证

MIT License — 详见 [LICENSE](LICENSE)
