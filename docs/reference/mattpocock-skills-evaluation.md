# mattpocock/skills → Hermes 评估与蒸馏

> **源仓库**：`mattpocock/skills` (83.8k★, TypeScript, MIT)
> **评估日期**：2026-05-15
> **类型**：方法论技能包 — 不替代现有组件，增强 Agent 工作流质量
> **策略**：**选择性蒸馏**（不接入，提炼方法论嵌入 Hermes 治理规则）

---

## 1. 源项目总览

| 维度 | 数据 |
|---|---|
| Stars | 83.8k (Agent 技能生态已验证的顶流) |
| License | MIT ✅ (可安全蒸馏) |
| 技能数 | 18 个 (工程 10 + 效率 4 + 杂项 4) |
| 安装方式 | `npx skills@latest add mattpocock/skills` |
| 设计哲学 | 小、可组合、可修改、不限模型 |
| 理论基础 | Pragmatic Programmer + DDD + XP |

---

## 2. 核心方法论（4 个痛点 → 4 个修复）

| # | 痛点 | 修复 | Hermes 相关性 |
|---|---|---|---|
| 1 | **沟通不对齐** — Agent 没理解你要什么 | `/grill-me` + `/grill-with-docs` 深度审讯 | 🔴 我们的 agent 直接跳执行 |
| 2 | **术语不统一** — 输出冗长像废话 | `CONTEXT.md` 共享语言 + ADR 决策记录 | 🔴 跨 agent 术语混乱 |
| 3 | **缺反馈循环** — 代码永远不工作 | `/tdd` 红绿重构 + `/diagnose` 调试循环 | 🟡 已有测试，缺纪律 |
| 4 | **代码熵增** — 越来越乱 | `/improve-codebase-architecture` 定期保养 | 🟡 平台在膨胀 |

---

## 3. 技能矩阵：Hermes 匹配度

### 🔴 高优先级 — 立即蒸馏到 Hermes 治理规则

| 技能 | 功能 | Hermes 嵌入点 |
|---|---|---|
| **`/grill-with-docs`** | 审讯计划 + 构建共享语言 + ADR | `os/governance/agent-alignment-rules.md` → 所有 agent 启动前必须先对齐 |
| **`/handoff`** | Agent-to-agent 交接文档 | `os/governance/handoff-protocol.md` → 跨 agent 任务移交标准化 |
| **`CONTEXT.md`** | 项目术语表 + 领域语言 | `os/active/projects/hermes-platform/CONTEXT.md` → 统一术语 |

### 🟡 中优先级 — 作为方法论参考

| 技能 | 功能 | Hermes 用法 |
|---|---|---|
| **`/tdd`** | 红-绿-重构循环 | 增强 `tests/` 规范，添加 TDD 治理检查 |
| **`/improve-codebase-architecture`** | 代码库架构保养 | 作为 cron 周任务 (`friday-org-review` 追加) |
| **`/diagnose`** | 调试纪律循环 | 嵌入 `systematic-debugging` 技能 |
| **`/prototype`** | 一次性原型 | 我们已有 `spike` skill，可增强 |
| **`/to-prd`** | 对话→PRD | Discovery board 产出规范化 |

### ⚪ 低优先级 — 参考但不蒸馏

| 技能 | 原因 |
|---|---|
| `/caveman` | 已被我们的 SymbolicMemory (Phase C) 覆盖 |
| `/triage` | GitHub Issues 流程 — 备用 |
| `/to-issues` | PRD→Issues 分解 — 备用 |
| `/zoom-out` | 代码解释 — 通用好实践 |
| `/git-guardrails-claude-code` | Claude Code 特化 — 不适用 |
| misc 技能 | TS 特化工具 — 不适用 |

---

## 4. 最高价值提取：共享语言 (CONTEXT.md + ADR)

这是 Matt 描述的"最酷的技巧"——也是 Hermes 组织当前最缺的能力。

### 当前问题

```
Hermes 组织跨 agent 对话中：
- "修正" 在不同 agent 中有不同含义 (correction vs revision vs fix)
- "snapshot" 被 3 个 agent 以 3 种方式使用
- "capsule" 格式不统一 (JSON vs Markdown vs 混合)
- Agent 之间交接任务时，上下文丢失率高
```

### 蒸馏方案

创建 `CONTEXT.md` 作为 Hermes 平台的**统一术语表**：

```markdown
# Hermes Platform — Shared Language (CONTEXT.md)

## Domain Terms
- **WorldAction** = 组织级行动记录，格式 JSON，路径 os/world/snapshot/
- **Capsule** = 知识摄入胶囊，格式 JSON，路径 os/active/capsules/
- **Tier** = Memory v2 四层架构中的一层 (L0-L3)
- **Distillation** = 从原始数据逐层提取结构化知识的过程
- **Correction** = CEO 或 human 对 agent 输出的修正指令
- **Governance Rule** = 不可被 agent 修改的组织约束
- **Coworker** = 被 Hermes 编排系统管理的子 agent 进程

## Architecture Decisions (ADR)
- ADR-001: 选择 4-tier Memory (TencentDB 蒸馏) 而非 flat file
- ADR-002: 零外部 npm 依赖 (Phase A-C 纯 Python)
- ADR-003: 渐进披露 → 默认注入 L3，需要时 drill-down
```

---

## 5. 蒸馏实施路线

| 步骤 | 内容 | 估时 | 产出 |
|---|---|---|---|
| **Step 1** | 创建 `CONTEXT.md` 术语表 | 30m | `os/active/projects/hermes-platform/CONTEXT.md` |
| **Step 2** | 写入 ADR-001/002/003 | 30m | `docs/adr/` 目录 + 3 个决策记录 |
| **Step 3** | 创建 Agent 对齐规则 | 1h | `os/governance/agent-alignment-rules.md` |
| **Step 4** | 创建 Handoff 协议 | 30m | `os/governance/handoff-protocol.md` |

---

## 6. 与现有技能的关系

| 现有 Hermes 技能 | mattpocock 对应 | 关系 |
|---|---|---|
| `native-feel-skill` (#8, A/85) | — | native-feel 是 UI 质量标准，mattpocock 是工程流程标准 → **互补** |
| `systematic-debugging` | `/diagnose` | 功能重叠 → 用 mattpocock 方法论增强 |
| `spike` | `/prototype` | 功能重叠 → 保留 spike，吸收 prototype 的"多个变体"技巧 |
| `hermes-workspace-dev` | — | 平台自身开发流程 |

---

## 7. 决策

| 决策 | 结论 |
|---|---|
| 是否接入为 Registry Skill？ | ✅ 作为 #9，评级 A/88（方法论级，高于工具级） |
| 是否接入 npm 包？ | ❌ 不接入 npm（方法论蒸馏，不依赖外部运行时） |
| 是否替换现有 skill？ | ❌ 增强，不替换 |
| 优先级 | 🔴 最高 — Step 1-4 全部可以在 2.5h 内完成 |

---

## 8. 参考链接

- 源仓库：https://github.com/mattpocock/skills
- Newsletter：https://www.aihero.dev/s/skills-newsletter (60k+ 订阅)
- 安装：`npx skills@latest add mattpocock/skills`
- License：MIT
