# Hermes Workspace — 竞品格局与差异定位

> 2026-05-14 晚间推演产物 · 基于 47 条 Algolia + 14 条 GitHub 信号 + 2 家深度竞品分析

## 竞品矩阵

| 产品 | ★ | 类型 | 格式 | 执行层 | 部署 | 市场 | 治理 |
|------|:--:|------|------|:------:|------|------|:----:|
| **Hermes Workspace** | — | 工作空间 + 运行时 | SKILL.md v1 | ✅ 原生 | Docker/SQLite | 全球 | 灵活分级 |
| **iFlytek SkillHub** | 3,331 | 纯 Registry | SKILL.md | ❌ 依赖外部 | Java/PostgreSQL/Redis/S3 | 中国/iFlytek | 强制人工审核 |
| **skills-manager** | 1,415 | 桌面管理工具 | 多格式 | ❌ 仅同步 | Electron 桌面 | 全球 | 无 |
| **SkillDock** | 51 | 桌面控制中心 | 多格式 | ❌ 仅管理 | 桌面应用 | 全球 | 无 |
| **Claude for SB** | — | SMB SaaS 平台 | Anthropic 专用 | ✅ 内置 | SaaS (Anthropic) | 全球 SMB | 内置审批流 |
| **Moxt.ai** | — | SaaS 工作空间 | 自定义 | ✅ 内置 | SaaS (闭源) | 全球 | 积分黑箱 |
| **Claude Design** | 242/d | 技能包 | Claude 专用 | ❌ 依赖 Claude | — | 全球 | 无 |

## iFlytek SkillHub 深度分析（3,331★）

### 它是什么
企业级、自部署、开源的 Agent 技能 Registry。**只是 Registry，不是工作空间。**

### 5 层架构拆解
1. **技能格式** — 使用 SKILL.md（YAML frontmatter + Markdown body），与 Hermes 兼容
2. **治理** — 4 种平台角色 + 3 种命名空间角色 + 4 种访问策略 + 完整审计日志
3. **审核流程** — 发布 → PENDING_REVIEW → 管理员审批 → PUBLISHED/REJECTED
4. **部署** — Java 21 + Spring Boot + PostgreSQL 16 + Redis 7 + S3/MinIO（4 服务最低）
5. **市场** — 中国优先（阿里云镜像、企业微信群、中文文档），次要国际化

### Hermes 8 维差异化优势

| # | 差异维度 | SkillHub | Hermes Workspace |
|:--:|----------|----------|------------------|
| 1 | **Registry vs 工作空间** | 纯仓库（存/版本/发现/下载） | **Registry + 运行时 + 工作空间** — 不只是找技能，直接使用 |
| 2 | **静态 vs 可执行** | 静态 Markdown 文件（zip） | **可执行、参数化、运行时感知** — 技能可以调用工具、链式执行 |
| 3 | **部署复杂度** | Java + PostgreSQL + Redis + S3（4 服务） | **Docker 一键部署** — 单容器启动，轻量化 |
| 4 | **市场定位** | 中国优先，iFlytek 生态绑定 | **全球优先** — 英文为主，平台无关 |
| 5 | **审核模式** | 强制人工审核（PENDING_REVIEW） | **灵活分级** — 信任发布/自动验证/可选人工审核 |
| 6 | **AI 能力** | 零 AI 特性（传统 CRUD） | **AI 原生** — 技能创建建议、去重检测、语义搜索、自动组合 |
| 7 | **多租户** | 单实例共享（命名空间隔离） | **真正多租户/工作空间隔离** — 每团队独立策略和配额 |
| 8 | **技能沙箱** | 无测试环境 | **内置技能沙箱** — 发布前在临时环境中试运行 |

### 结论
iFlytek SkillHub 是企业级技能仓库的标杆——治理完备、格式标准（已采用 SKILL.md）、开源自部署。但它是「仓库」，不是「工作空间」。Hermes 的差异化不在格式竞争上，而在「技能的生命周期全链路」——从创建、扫描、审计到执行、共享、治理，Hermes 是一站式闭环，SkillHub 只是其中一环。

**竞争战略**：不竞争 SKILL.md 格式标准（SkillHub 已采用，证明格式正确），竞争「端到端体验」——用户从发现技能到使用技能只需一次点击，不需要部署第二个平台。

## skills-manager（1,415★）— 桌面工具

跨 15+ 工具的轻量桌面技能管理器。不与 Hermes 竞争——它是同步工具，不是平台。互补机会：Hermes 可以作为它支持的第 16 个工具。

## 战略含义

1. **SKILL.md 正成为事实标准** — iFlytek（3,331★）和多个独立工具已采用相同格式。Hermes 的格式选择已验证。
2. **Registry 层已有巨头** — 3,331★ 的 iFlytek 意味着「纯 Registry」赛道窗口正在关闭。Hermes 不应竞争 Registry，而应竞争「Registry + Runtime」。
3. **内容窗口最宽** — Claude Design（242★/d）证明技能消费市场活跃。Hermes 的 Registry 应优先收录优质技能，而非建设 Registry 功能。
4. **全球市场空白** — 中文生态有 iFlytek（3,331★）和 skills-manager（1,415★），英文生态有 SkillDock（51★）。英文市场的「Registry + Runtime」一体化产品尚空缺。
