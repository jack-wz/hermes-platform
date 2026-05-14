# Claude Code `/goal` 技术评估

> 2026-05-14 · P1 评估（48h 窗口） · 确认：无需产品响应

---

## 技术架构

### `/goal` 工作原理

1. 用户设定完成条件（最多 4000 字符），如 `all tests in test/auth pass and lint is clean`
2. Claude 开始执行任务
3. **每轮结束后，一个独立的小型快速模型（evaluator）判断条件是否达成**
4. Evaluator **仅读取对话记录（transcript）** — 不运行命令、不读文件、不调用工具
5. 条件达成 → `/goal` 自动结束。未达成 → Claude 继续下一轮
6. 单 session 内有效，session 结束即清除

### 关键约束

| 属性 | `/goal` | Hermes delegate_task + cron |
|------|:------:|:---------------------------:|
| **执行跨度** | 单 session | 跨 session、跨天 |
| **工具调用** | ✅ Claude 本体 | ✅ 完整工具集 |
| **Evaluator 工具调用** | ❌ **不可调用** | ✅ delegate 可以再次委托 |
| **Evaluator 文件访问** | ❌ **仅读 transcript** | ✅ 读文件、检查状态 |
| **多步骤编排** | 线性执行直到条件满足 | DAG 依赖、并行、条件分支 |
| **调度** | 手动 `/goal` | Cron 定时触发 |
| **审计** | 无内置审计 | hermes-audit 收据系统 |
| **安全扫描** | 无（Claude 内置安全） | hermes-scan A-F 评级 |
| **Session 持久** | ❌ Session 结束后丢失 | ✅ Log 持久化 + 内存 |

## 竞争评估

### 不构成直接威胁的原因

1. **Evaluator 无工具调用** — 这是架构性约束，不是临时限制。Evaluator 运行在 Anthropic 基础设施上，没有外部访问。这意味着 `/goal` 无法验证「文件是否存在」「API 是否返回 200」「数据库是否更新」— 只能验证「Claude 在对话中说它做完了」。

2. **单 Session 限制** — `/goal` 在 session 结束后清除。Hermes cron 可以连续运行数天，跨 session 传递状态。

3. **无编排** — `/goal` 是线性循环。Hermes delegate_task 支持并行子代理、依赖门控、条件分支。

### 差异化优势

```
/goal:   "Keep working until tests pass" (单 session, evaluator 不能验证测试结果)
Hermes:  "Every morning at 7am, scan HN, score signals, 
          trigger coworker if score > 80, log to audit trail,
          send report to CEO" (跨 session, 多工具, 全审计)
```

### 触发升级条件

- **P0 if**: Evaluator 获得 MCP tool-calling 能力 → `/goal` 变成真正的自主执行引擎
- **P1 if**: `/goal` 支持跨 session 持久化 → 与 Hermes cron 功能重叠
- **No action if**: `/goal` 保持当前架构（评估器只读 transcript）

**当前状态**: 无升级触发。

## 推荐行动

1. **不改变产品路线** — `/goal` 不是为了与 Hermes 竞争，而是为了减少 Claude Code 用户的手动提示。
2. **差异化叙事** — 在文档和内容中强调 Hermes 的「跨 session、多工具、全审计」vs `/goal` 的「单 session、线性、无审计」。
3. **技术监控** — 跟踪 Anthropic 是否宣布 evaluator 的 MCP 工具调用支持（低概率，但跟踪即可）。
