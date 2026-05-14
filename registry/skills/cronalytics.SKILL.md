---
skill_id: monitoring/cronalytics
version: 1.0.0
author:
  name: 8bit64k
  display: 8bit64k
  contact: https://github.com/8bit64k/cronalytics/issues
description: >
  Hermes Agent 原生 cron 可观测性插件。提供 cron job 的执行成本追踪、
  成功率监控和异常告警。适合需要了解 agent 定时任务运行成本的团队。
  触发条件：Hermes Agent 运行中自动激活。

permissions:
  filesystem:
    read:
      - "~/.hermes/cron/jobs.json"
      - "~/.hermes/cron/runs/"
      - "~/.hermes/logs/gateway.log"
    write: []

  network:
    domains: []
    ports: []
    protocols: []

  tools:
    - terminal
    - file

  credentials: []

cost:
  token_estimate:
    base: 200
    per_run:
      input: 500
      output: 200
      total: 700
  api_cost_risk: LOW
  rate_limits:
    max_calls_per_hour: 4
    max_calls_per_day: 24
    retry_strategy: exponential_backoff

input:
  required: []
  optional:
    - name: lookback_hours
      type: integer
      description: 回溯时间（小时），默认 24
      default: 24
    - name: alert_threshold
      type: number
      description: 失败率告警阈值，默认 0.1
      default: 0.1

output:
  success:
    - name: total_jobs
      type: integer
      description: 总 job 数
    - name: success_rate
      type: number
      description: 成功率 (0.0-1.0)
    - name: total_cost_estimate
      type: number
      description: 估算总 token 消耗
    - name: failing_jobs
      type: array
      description: 失败 job 列表
  failure:
    - name: error
      type: string
      description: 错误信息
    - name: code
      type: integer
      description: 错误码

tags:
  - monitoring
  - cron
  - observability
  - cost-tracking
  - hermes-ecosystem

dependencies:
  - name: PyYAML
    version: ">=6.0"
    required: true

metadata:
  hermes:
    tags: [monitoring, cron, observability]
  external:
    repo: https://github.com/8bit64k/cronalytics
    license: MIT
    contact_issue: https://github.com/8bit64k/cronalytics/issues/4
    status: contact_initiated
    stars: 25
---

# Cronalytics

> Hermes Agent cron 可观测性插件 · [GitHub](https://github.com/8bit64k/cronalytics) · MIT

Cronalytics 为 Hermes Agent 提供 cron job 的执行成本追踪、成功率监控和异常告警。

## 状态

- ✅ 已发起合作讨论: [Issue #4](https://github.com/8bit64k/cronalytics/issues/4)
- ⏳ 等待作者回复
- 🎯 目标: 收录进 Hermes 官方插件市场
