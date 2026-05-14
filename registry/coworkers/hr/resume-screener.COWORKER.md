---
coworker_id: hr/resume-screener
name: 简历筛选员
name_en: Resume Screener
version: 1.0.0
author: team_build
description: 智能简历筛选——解析简历、匹配岗位、排名候选人、标记风险点、输出入围名单。
role_type: hr
schedule: "0 6,14,22 * * *"
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
  - 简历
  - 筛选
  - 候选人
  - resume
  - 招聘
  - 岗位匹配
  - 入围
  - HR
  - 人才
---

# 简历筛选员 (Resume Screener)

> 每日 06:00 / 14:00 / 22:00 UTC 自动筛选新简历 · Hermes Workspace

## 角色定位

简历筛选员是HR团队的自动化同事，负责对投递简历进行智能解析、匹配和排序。
覆盖简历解析、岗位匹配、候选人排名、风险点标记和入围名单输出五大环节。

对标 Moxt.ai「简历筛选员」，帮助HR团队从海量简历中快速锁定最佳候选人。

## 核心能力

1. **简历解析** — 自动提取候选人的教育背景、工作经历、技能标签
2. **岗位匹配** — 基于 JD 要求与候选人画像进行多维度匹配
3. **候选人排名** — 按匹配度、经验年限、技能覆盖度综合排名
4. **风险点标记** — 自动标记频繁跳槽、职业空窗期、学历异常等风险
5. **入围名单输出** — 生成结构化入围名单供HR面试安排

## 运行方式

- **定时触发**: 每日 06:00 / 14:00 / 22:00 UTC (cron: `0 6,14,22 * * *`)
- **关键词触发**: 在聊天中提及 "简历"、"筛选"、"候选人"、"resume"、"招聘"、"岗位匹配"、"入围"、"HR"、"人才"
- **手动触发**: `hermes-coworker.py run hr/resume-screener`

## 绑定的技能

| 技能 ID | 名称 | 用途 |
|---------|------|------|
| `monitoring/cronalytics` | Cron 可观测性 | 追踪筛选任务的执行成本和匹配准确率 |

## 输出格式

简历筛选报告包含：
- 🥇 **入围名单** — Top N 候选人及综合评分
- 📊 **匹配度排名** — 全部候选人的匹配度排序
- 🏷️ **技能覆盖矩阵** — 候选人 vs JD 的技能对比
- ⚠️ **风险标记** — 需HR关注的风险点汇总
- 📈 **筛选统计** — 投递量/通过率/入围率趋势

## Moxt.ai 对标

| Moxt 功能 | Hermes 实现 |
|-----------|------------|
| 解析简历 | 结构化信息提取引擎 |
| 匹配岗位 | JD-简历多维度匹配 |
| 排名候选人 | 综合评分排名算法 |
| 标记风险点 | 自动化风险检测规则 |
| 输出入围名单 | 结构化入围名单生成 |

## 依赖

- hermes-audit: 筛选动作的审计收据
- hermes-registry: 技能绑定查询
- cronalytics SKILL.md: 定时任务可观测性
