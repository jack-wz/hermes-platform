# Hermes + Obsidian + LLM Wiki 本地知识库架构

> 来源：Roland.W (@rwayne) · 2026-05-13  
> 原始链接：X/Twitter 文章

## 核心架构

```
文档导入 → Hermes Agent (AI 整理) → LLM Wiki (结构化) → Obsidian (可视化)
```

**三个工具，各有分工：**

| 工具 | 角色 | 职责 |
|------|------|------|
| **Hermes Agent** | 自动化执行引擎 | 接收指令、提取实体/概念、创建结构化文件、添加双向链接 |
| **LLM Wiki** | 知识库标准 | 定义文件结构规范（entities/concepts/index/log） |
| **Obsidian** | 笔记展示层 | 双向链接跳转、Graph View 知识网络可视化 |

## LLM Wiki 文件结构

```
knowledge_base/
├── raw/sources/          # 原始素材
├── wiki/entities/        # 实体（人物、工具、项目）
├── wiki/concepts/        # 概念（方法论、原理）
├── wiki/index.md         # 知识库索引
└── wiki/log.md           # 更新日志
```

## 三条核心规则

1. **说「写入知识库」→ Hermes 自动整理** — 提取实体/概念、创建 Markdown、添加双向链接
2. **说「结合知识库」→ Hermes 检索回答** — 基于知识库整合答案，标注来源
3. **Obsidian 随时可用** — 知识库目录直接作为 Vault，双链浏览

## 与 Hermes Workspace 的映射

| Roland.W 方案 | Hermes Workspace 对应 |
|---------------|---------------------|
| Hermes Agent (执行引擎) | Coworker Engine + 8 coworkers |
| LLM Wiki (文件结构) | SKILL.md v1 + registry + 命名空间 |
| Obsidian (可视化) | Dashboard (5002) + bidirectional links |
| "写入知识库" 触发 | `/api/memory` POST + sandbox test |
| "结合知识库" 检索 | `/api/memory/context` + `/api/memory/search` |
| 本地存储 | 自托管 Docker + 本地文件系统 |

## 战略含义

1. **个人知识管理是团队工作空间的入口** — 用户从个人 PKM 自然过渡到团队协作
2. **双向链接是粘性功能** — Obsidian 的 [[wikilinks]] 让用户离不开
3. **LLM Wiki 格式是互补标准** — 可与 SKILL.md 共存，覆盖个人知识管理场景
4. **「只说就做」是核心体验** — 用户不需要手动操作图形界面

## 优化方向

- [x] LLM Wiki 文件结构支持（`hermes-knowledge.py`）
- [x] Knowledge Curator coworker（第 9 个 AI 同事）
- [x] Obsidian 兼容 [[双向链接]] 输出
- [ ] Hermes Workspace Vault → Obsidian 一键导入
