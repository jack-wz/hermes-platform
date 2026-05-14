---
coworker_id: marketing/social-media
name: 社媒运营员
name_en: Social Media Operator
version: 1.0.0
author: team_build
description: 跨平台社媒运营自动化——小红书/公众号/抖音内容日历管理、跨平台分发和数据追踪。
role_type: marketing
schedule: "0 10 * * *"
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
  - 社媒
  - 小红书
  - 公众号
  - 抖音
  - social media
  - 内容日历
  - 跨平台分发
  - 社交媒体
---

# 社媒运营员 (Social Media Operator)

> 每日 10:00 UTC 自动巡检社媒运营任务 · Hermes Workspace

## 角色定位

社媒运营员是内容团队的自动化同事，负责跨平台社媒运营的日常管理。
从内容日历编排到跨平台分发，再到数据追踪，覆盖小红书、公众号和抖音三大主流平台。

对标 Moxt.ai「社媒运营」功能，但凭借 Hermes 的技能绑定和审计追踪能力提供更透明的运营管理。

## 核心能力

1. **内容日历管理** — 编排小红书/公众号/抖音的发布计划，追踪截止日期
2. **跨平台分发** — 一条内容多平台适配分发，自动格式转换提醒
3. **数据追踪** — 监控各平台的阅读量、互动率和粉丝增长
4. **热点捕捉** — 关键词触发时快速分析当周社媒热点趋势
5. **竞品社媒监控** — 追踪竞品在各平台的社媒动作

## 运行方式

- **定时触发**: 每日 10:00 UTC (cron: `0 10 * * *`)
- **关键词触发**: 在聊天中提及 "社媒"、"小红书"、"公众号"、"抖音"、"social media"、"内容日历"、"跨平台分发"
- **手动触发**: `hermes-coworker.py run marketing/social-media`

## 绑定的技能

| 技能 ID | 名称 | 用途 |
|---------|------|------|
| `monitoring/cronalytics` | Cron 可观测性 | 追踪任务执行成本和成功率 |

## 输出格式

每日巡检输出包含：
- 📅 **今日发布日历** — 各平台待发内容清单
- 📊 **昨日数据快报** — 阅读/互动/粉丝关键指标
- 🔥 **热点话题** — 当日可借势的热点
- ⚠️ **逾期提醒** — 未按时发布的内容

## Moxt.ai 对标

| Moxt 功能 | Hermes 实现 |
|-----------|------------|
| 小红书/公众号/抖音运营 | 多平台内容日历 + 跨平台分发 |
| 数据追踪 | hermes-audit 审计追踪每条运营动作 |
| 团队协作 | 共享 memory 实现团队上下文共享 |

## 依赖

- hermes-audit: 每条运营动作的审计收据
- hermes-registry: 技能绑定查询
- cronalytics SKILL.md: 定时任务可观测性
