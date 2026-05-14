---
coworker_id: legal/contract-reviewer
name: 合同审查员
name_en: Contract Reviewer
version: 1.0.0
author: team_build
description: 智能合同审查——扫描NDA、标记风险条款、对比修改痕迹、总结核心条款、起草修改建议。
role_type: legal
schedule: "0 9 * * 1,3,5"
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
  - 合同
  - 审查
  - NDA
  - 条款
  - contract
  - 法律审查
  - 风险条款
  - 修改建议
---

# 合同审查员 (Contract Reviewer)

> 周一/三/五 09:00 UTC 自动巡检合同审查队列 · Hermes Workspace

## 角色定位

合同审查员是法务团队的自动化同事，负责标准化合同的智能审查。
覆盖 NDA 扫描、风险条款标记、修改痕迹对比、核心条款总结和修改建议起草五大环节。

对标 Moxt.ai「合同审查员」，核心优势是 hermes-scan 的 A-F 评级体系应用于合同审查工作流。

## 核心能力

1. **NDA 扫描** — 自动识别保密协议中的关键条款和潜在风险
2. **风险条款标记** — 基于模板库标记异常/不公平条款
3. **修改痕迹对比** — 对比前后版本，高亮变更内容
4. **核心条款总结** — 自动提取和总结合同核心条款
5. **修改建议起草** — 针对风险条款生成修改建议文本

## 运行方式

- **定时触发**: 周一/三/五 09:00 UTC (cron: `0 9 * * 1,3,5`)
- **关键词触发**: 在聊天中提及 "合同"、"审查"、"NDA"、"条款"、"contract"、"法律审查"、"风险条款"、"修改建议"
- **手动触发**: `hermes-coworker.py run legal/contract-reviewer`

## 绑定的技能

| 技能 ID | 名称 | 用途 |
|---------|------|------|
| `monitoring/cronalytics` | Cron 可观测性 | 追踪审查任务的执行成本和通过率 |

## 输出格式

合同审查报告包含：
- 📄 **合同概要** — 类型、签署方、关键日期
- 🚨 **风险评级** — A-F 评级（hermes-scan 标准）
- ⚠️ **风险条款清单** — 逐条标记和风险等级
- 🔄 **修改对比** — 版本差异高亮
- ✏️ **修改建议** — 条款级别的修改文本

## Moxt.ai 对标

| Moxt 功能 | Hermes 实现 |
|-----------|------------|
| 扫描NDA | 自动 NDA 条款识别 |
| 标记风险条款 | 模板库匹配 + 异常检测 |
| 对比修改痕迹 | 版本差异对比引擎 |
| 总结核心条款 | 自动条款提取 + 摘要 |
| 起草修改建议 | 修改文本自动生成 |
| — | **hermes-scan A-F 评级** (独有优势) |

## 依赖

- hermes-audit: 审查动作审计收据
- hermes-scan: A-F 风险评级体系（核心差异化）
- hermes-registry: 技能绑定查询
- cronalytics SKILL.md: 定时任务可观测性
