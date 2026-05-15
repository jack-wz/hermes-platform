# TencentDB Agent Memory → Hermes Memory v2 架构蒸馏

> **蒸馏源**：`Tencent/TencentDB-Agent-Memory` (1,494★, TypeScript, npm)
> **蒸馏日期**：2026-05-15
> **负责人**：team_skillops
> **策略**：B→A — 先蒸馏架构，再评估 npm 接入

---

## 1. 源架构精华

### 1.1 四层记忆管道 (L0 → L1 → L2 → L3)

| 层级 | 名称 | 存储 | 粒度 | 用途 |
|------|------|------|------|------|
| **L0** | Conversation | 原始对话文件 | 完整会话 | 证据源，不可丢失 |
| **L1** | Atom | 原子事实 (jsonl) | 单条信息 | 快速检索，去重提取 |
| **L2** | Scenario | 场景块 (Markdown) | 上下文模式 | 复用场景，SOP 模板 |
| **L3** | Persona | 用户画像 (Markdown) | 长期偏好 | 个性化，少样本注入 |

**关键洞察**：不是把所有信息压平进一个向量库，而是分层存储 + 逐层蒸馏。

### 1.2 符号化记忆 (Symbolic Memory)

- 将冗长工具日志（数万 token）提炼为 **Mermaid 符号图**
- 每个节点携带 `node_id`，可 drill-down 到原始日志
- Token 节省 61%（WideSearch 实测）

### 1.3 异构存储 + 渐进披露

- **底层**（DB）：事实、日志、轨迹 → 全文检索
- **顶层**（Markdown）：Persona、Scenario、Canvas → 人类可读、白盒审查
- **原则**：底层保留证据，顶层保留结构

### 1.4 完整可追溯链

```
L3 Persona (顶层符号)
  → L2 Scenario (中层索引)
    → L1 Atom (原子事实)
      → L0 Conversation (原始证据)
```

---

## 2. Hermes Memory 现状 (v1.2)

| 维度 | 当前实现 |
|------|----------|
| 存储 | 单文件 `SHARED_MEMORY.md` + 4 namespace |
| 结构 | 扁平条目（时间戳 + 作者 + 正文） |
| 检索 | 全文正则匹配 |
| 分层 | 无（命名空间仅做隔离，不做蒸馏） |
| 注入 | 原始条目注入 prompt（`get_team_context`） |

### 2.1 差距分析

| 能力 | TencentDB | Hermes v1.2 | 差距 |
|------|-----------|-------------|------|
| 分层管道 | L0→L3 四级 | 无 | 🔴 |
| 符号化压缩 | Mermaid canvas | 无 | 🔴 |
| 自动蒸馏 | L0→L1 提取 + 去重 | 无 | 🔴 |
| 渐进披露 | 顶层注入 + drill-down | 全量注入 | 🟡 |
| 向量检索 | embedding + hybrid | 无 | 🟡 |
| 可追溯 | node_id 全链路 | 原始引用 | 🟢 |

---

## 3. Hermes Memory v2 升级方案

### 3.1 目标架构（渐进式，不依赖外部 npm）

```
Phase A — 分层存储（本周）
  SHARED_MEMORY.md 拆分为层级目录：
  memory/
    l0-conversations/     # 原始对话 (keep existing format)
    l1-atoms/             # 原子事实 (jsonl, per-session)
    l2-scenarios/         # 场景块 (Markdown)
    l3-personas/          # 用户画像 (Markdown)

Phase B — 自动蒸馏管道
  - L0→L1: 每会话结束，提取原子事实 → jsonl
  - L1→L2: 每 5 会话，聚类原子事实 → 场景块
  - L2→L3: 每 50 会话，合成场景 → 用户画像
  - 可选 embedding 向量化（OpenAI 兼容）

Phase C — 符号化压缩
  - 会话内部：工具日志 → Mermaid symbol graph
  - node_id 索引 → 原始日志 drill-down
  - Token 节省目标：30-50%

Phase D — npm 接入评估
  - 评估 @tencentdb-agent-memory/memory-tencentdb 直接接入
  - 对比自主实现 vs npm 包的成本/收益
```

### 3.2 关键设计原则

1. **证据不丢失**：L0 始终保留原始对话
2. **顶层可读**：L3 Persona 为人类可读 Markdown
3. **渐进注入**：默认只注入 L3，需要细节时 drill-down
4. **无外部依赖启动**：Phase A-C 纯 Python，零 npm 依赖
5. **兼容现有 API**：保持 `read_memory()`, `write_memory()`, `get_team_context()` 接口不变

---

## 4. 实施路线

| Phase | 内容 | 估时 | 依赖 |
|-------|------|:----:|------|
| **A** | 分层目录 + 文件存储 | 1-2h | 无 |
| **B** | 蒸馏管道 (L0→L1→L2) | 3-4h | Phase A |
| **C** | 符号化 + token 优化 | 2-3h | Phase B |
| **D** | npm 包评估 + 接入决策 | 1h | Phase C |

> **2026-05-15 更新**: Phase A-C 已完成。Phase D 评估如下。

---

## 5. Phase D — npm 接入评估 (2026-05-15)

### 5.1 评估基准

| 维度 | @tencentdb-agent-memory (npm) | Hermes Memory v2 (自研) |
|---|---|---|
| **License** | MIT ✅ (已变更，原为 "Other") | MIT |
| **语言/运行时** | TypeScript, Node >= 22.16 | Python 3.11+ |
| **安装方式** | `openclaw plugins install @tencentdb-agent-memory/memory-tencentdb` | `import hermes_memory` |
| **存储后端** | SQLite + sqlite-vec | 文件系统 (Markdown + JSONL) |
| **L0-L3 分层** | ✅ | ✅ (蒸馏自同一架构) |
| **符号化压缩** | Mermaid canvas + `node_id` | Mermaid graph + `node_id` (Phase C) |
| **自动蒸馏** | LLM-based 提取 | 启发式 regex 提取 (Phase B) |
| **向量检索** | sqlite-vec embedding | 无（渐进披露代替检索） |
| **Hermes 兼容** | 有 badge，但需 npm 桥接 | 原生 Python，零桥接 |
| **基准数据** | WideSearch +61% pass, -61% tokens | 未跑基准 |
| **维护负担** | 依赖上游更新 | 完全自主 |

### 5.2 决策

| 维度 | 结论 |
|---|---|
| **是否现在接入 npm？** | ❌ 不接入 |
| **原因** | (1) 功能覆盖 ~80% — 我们的 Phase A-C 已实现核心架构；(2) 引入 Node.js 运行时增加运维复杂度；(3) 启发式提取虽不如 LLM-based，但零外部依赖的优势在当前阶段更大 |
| **未来路径** | ✅ 标记为可选插件 — License 已变 MIT，可在 Marketplace 中提供 `@tencentdb-agent-memory` 作为增强选项（当需要 LLM-based 提取和向量检索时） |
| **ADR 影响** | ADR-002 (零 npm 核心依赖) 维持有效，追加：Phase D 确认 npm 包为可选增强而非核心依赖 |

### 5.3 Memory v2 最终状态

```
Phase A — 分层目录结构       ✅ (66aa92e)
Phase B — 蒸馏管道            ✅ (66c54d8)
Phase C — 符号化压缩          ✅ (40495fd)
Phase D — npm 接入评估        ✅ (本次) → 决策：自维护，npm 为可选增强
```

**Memory v2 全阶段完成。** 🎉

---

## 6. 参考链接

- 源仓库：https://github.com/Tencent/TencentDB-Agent-Memory
- SKILL.md：安装配置完整指南
- hermes-plugin：`hermes-plugin/memory/memory_tencentdb/` (hooks: on_memory_write, on_session_end)
