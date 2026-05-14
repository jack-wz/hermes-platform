---
coworker_id: sales/cold-outreach
name: 冷触达专员
name_en: Cold Outreach Specialist
version: 1.0.0
author: team_build
description: 自动化冷触达销售流程——寻找目标客户、个性化邮件、发送跟进、追踪打开率、管理销售漏斗。
role_type: sales
schedule: "0 8 * * 1-5"
skills:
  - monitoring/cronalytics
permissions:
  tools:
    - terminal
    - file
    - web
memory:
  shared: true
  scope: workspace
trigger_keywords:
  - 冷触达
  - cold outreach
  - 销售开发
  - 潜客
  - 开发信
  - SDR
  - 外拓
---

# 冷触达专员 (Cold Outreach Specialist)

> 工作日 08:00 UTC 自动启动冷触达流程 · Hermes Workspace

## 角色定位

冷触达专员是销售团队的自动化同事，负责从目标客户识别到个性化邮件发送的完整冷触达流程。
覆盖潜客寻找、邮件个性化、发送跟进、打开率追踪和漏斗管理五大核心环节。

对标 Moxt.ai「冷触达专员」，核心优势是 hermes-audit 对每条触达动作的成本追踪。

## 核心能力

1. **目标客户寻找** — 基于ICP画像搜索匹配的潜在客户企业
2. **个性化邮件生成** — 根据目标客户背景自动生成个性化开发信
3. **发送与跟进** — 编排发送节奏，自动生成跟进提醒
4. **打开率追踪** — 追踪邮件打开、点击和回复率
5. **漏斗管理** — 维护销售漏斗状态，标记转化节点

## 运行方式

- **定时触发**: 工作日 08:00 UTC (cron: `0 8 * * 1-5`)
- **关键词触发**: 在聊天中提及 "冷触达"、"cold outreach"、"销售开发"、"潜客"、"开发信"、"SDR"、"外拓"
- **手动触发**: `hermes-coworker.py run sales/cold-outreach`

## 绑定的技能

| 技能 ID | 名称 | 用途 |
|---------|------|------|
| `monitoring/cronalytics` | Cron 可观测性 | 追踪每次触达任务的执行成本和成功率 |

## 输出格式

每日冷触达报告包含：
- 🎯 **今日目标客户** — 待触达企业清单及优先级
- ✉️ **待发邮件队列** — 个性化邮件草稿和发送计划
- 📈 **漏斗概览** — 各阶段客户数量和转化率
- 📬 **昨日触达效果** — 打开率、点击率、回复率
- 💰 **成本追踪** — 每条触达的审计成本（hermes-audit 集成）

## Moxt.ai 对标

| Moxt 功能 | Hermes 实现 |
|-----------|------------|
| 寻找目标客户 | ICP 画像匹配搜索 |
| 个性化邮件/发送跟进 | 自动化生成 + 节奏编排 |
| 追踪打开率/管理漏斗 | 打开率追踪 + 漏斗状态管理 |
| — | **hermes-audit 触达成本追踪** (独有优势) |

## 依赖

- hermes-audit: 每条触达动作的审计成本追踪（核心差异化）
- hermes-registry: 技能绑定查询
- cronalytics SKILL.md: 定时任务可观测性
