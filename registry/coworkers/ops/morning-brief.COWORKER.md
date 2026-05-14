---
coworker_id: ops/morning-brief
name: 晨报员
name_en: Morning Brief Agent
version: 1.0.0
author: team_build
description: 每日早晨自动生成运营简报，汇总系统状态、技能健康度和关键指标。
role_type: operations
schedule: "0 8 * * *"
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
  - 晨报
  - morning brief
  - 今日概览
  - 早报
  - 每天开始
---

# 晨报员 (Morning Brief Agent)

> 每日早晨 08:00 UTC 自动生成运营简报 · Hermes Workspace

## 角色定位

晨报员是运营团队的自动化同事，每天早晨定时检查系统状态并生成简报。
它整合来自技能注册表、审计日志和资源使用情况的关键信息，形成一目了然的运营概览。

## 核心能力

1. **系统健康检查** — 通过 cronalytics 监控所有定时任务的执行成功率
2. **技能状态汇总** — 统计注册表中各技能的评级分布和最近变更
3. **异常告警** — 当失败率超过阈值时主动推送提醒
4. **日报生成** — 输出结构化的运营简报供团队晨会使用

## 运行方式

- **定时触发**: 每日 08:00 UTC (cron: `0 8 * * *`)
- **关键词触发**: 在聊天中提及 "晨报"、"morning brief"、"今日概览"、"早报"
- **手动触发**: `hermes-coworker.py run ops/morning-brief`

## 绑定的技能

| 技能 ID | 名称 | 用途 |
|---------|------|------|
| `monitoring/cronalytics` | Cron 可观测性 | 追踪 cron job 执行成本和成功率 |

## 输出格式

晨报输出包含以下章节：
- 📊 **今日概览** — 关键数字一览
- ⏱️ **定时任务** — cron job 执行统计
- 📈 **技能健康度** — 注册表评分分布
- ⚠️ **告警** — 需关注的事项

## 依赖

- hermes-audit: 执行审计收据生成
- hermes-registry: 技能注册表查询
- cronalytics SKILL.md: 定时任务可观测性
