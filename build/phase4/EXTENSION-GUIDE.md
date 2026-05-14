# Hermes 平台扩展开发指南

> **面向开发者**：如何为 Hermes 平台编写技能、提交扫描、查看审计回执、以及通过 Plugin Bridge 扩展平台能力。
>
> 版本：1.0.0 | 维护者：team_build（技术开发·工匠长）| 日期：2026-05-14

---

## 目录

1. [Hermes 平台概述](#1-hermes-平台概述)
2. [技能格式：SKILL.md v1.0](#2-技能格式skillmd-v10)
3. [静态扫描：hermes-scan](#3-静态扫描hermes-scan)
4. [审计回执：hermes-audit](#4-审计回执hermes-audit)
5. [Plugin Bridge：扩展系统](#5-plugin-bridge扩展系统)
6. [三个 Hook 详解](#6-三个-hook-详解)
7. [部署与配置](#7-部署与配置)
8. [最佳实践](#8-最佳实践)
9. [附录](#9-附录)

---

## 1. Hermes 平台概述

Hermes 是 OpenClaw 组织操作系统中的**技能生命周期管理平台**。它提供从技能编写、安全审计、执行追踪到生态扩展的全链路支持。

### 平台架构（四个阶段）

```
┌──────────────────────────────────────────────────────┐
│  Phase 1: SKILL.md v1.0 格式规范                      │
│  ├─ YAML frontmatter（8 个必选字段 + 6 个可选字段）    │
│  ├─ Markdown body（技能指令与实现）                     │
│  └─ 示例技能：devops/backup/git-auto-backup            │
├──────────────────────────────────────────────────────┤
│  Phase 2: hermes-scan 静态扫描器                       │
│  ├─ 结构验证（§4.1）：字段完整性、格式校验               │
│  ├─ 安全验证（§4.2）：权限范围、凭据声明、通配符检测     │
│  ├─ 契约验证（§4.3）：输入/输出/cost 契约完整性          │
│  └─ A-F 评级（0-100 分）← 自动生成                     │
├──────────────────────────────────────────────────────┤
│  Phase 3: hermes-audit 审计回执生成器                   │
│  ├─ 包装技能执行命令                                    │
│  ├─ 关联 hermes-scan 评级                              │
│  ├─ 记录时间戳、退出码、SHA-256 输入哈希                 │
│  └─ 输出签名 JSON 回执（可验证、防篡改）                 │
├──────────────────────────────────────────────────────┤
│  Phase 4: Plugin Bridge + 扩展指南  ← 本文档           │
│  ├─ 3 个核心 Hook：pre / post / error                  │
│  ├─ 插件注册与配置                                      │
│  └─ 开发者文档与最佳实践                                │
└──────────────────────────────────────────────────────┘
```

### 核心设计原则

| 原则 | 说明 |
|------|------|
| **安全优先** | 权限声明必须精确到路径/域名级别，禁止通配符 |
| **可审计** | 每次执行生成签名回执，SHA-256 保证完整性 |
| **可扩展** | Plugin Bridge 支持第三方插件热注册 |
| **人类可写** | SKILL.md 纯文本格式，无需专用工具 |

---

## 2. 技能格式：SKILL.md v1.0

### 2.1 文件结构

每个技能是一个以 `.SKILL.md` 结尾的 Markdown 文件，由两部分组成：

```yaml
---
# YAML frontmatter — 元数据声明
skill_id: devops/backup/git-auto-backup
version: 1.0.0
author:
  name: team_build
  display: 技术开发·工匠长
  contact: build@hermes.internal
description: >
  自动备份指定目录到远程 Git 仓库……
permissions:
  filesystem:
    read: ["~/.hermes/workspace/**"]
    write: ["~/.hermes/backups/repos/"]
  network:
    domains: ["github.com", "api.github.com"]
    ports: [443]
    protocols: ["https"]
  tools: [terminal, file]
  credentials:
    - name: GITHUB_TOKEN
      type: env
      scope: repo
      required: true
cost:
  token_estimate:
    base: 600
    per_run:
      input: 2500
      output: 1500
      total: 4000
  api_cost_risk: LOW
input:
  required:
    - name: target_directory
      type: string
      description: 需要备份的目标目录绝对路径
      validation: "^/[a-zA-Z0-9/._-]+$"
  optional:
    - name: branch
      type: string
      description: 推送目标分支
      default: "main"
output:
  success:
    description: 备份成功完成
    schema:
      backup_id: "string"
      commit_hash: "string"
  failure:
    description: 备份失败
    schema:
      error_code: "string"
      error_message: "string"
      recoverable: "boolean"
---
# 技能实现说明（Markdown）

## 触发条件
- 手动调用
- Cron 定时触发
……
```

### 2.2 必选字段速查

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `skill_id` | string | 全局唯一标识，三段式命名 | `devops/backup/git-auto-backup` |
| `version` | string | SemVer 版本号 | `1.0.0` |
| `author` | string/object | 责任人信息 | `team_build <build@hermes.internal>` |
| `description` | string | 功能描述（20-500 字符） | `自动备份指定目录到远程 Git 仓库……` |
| `permissions` | object | 权限声明（文件系统/网络/工具/凭据） | 见上方示例 |
| `cost` | object | 成本声明（token 估算 + API 风险等级） | 见上方示例 |
| `input` | object | 输入参数契约 | 见上方示例 |
| `output` | object | 输出契约（成功/失败 schema） | 见上方示例 |

### 2.3 编写建议

1. **skill_id 命名**：用 `{领域}/{类别}/{名称}` 三段式，便于分类检索
2. **permissions 声明**：精确到路径，避免 `/**` 或 `*` 通配符（会导致评分下降）
3. **cost 估算**：诚实估算 token 消耗，`api_cost_risk` 选对等级
4. **input/output 契约**：每个参数声明 type，可选参数必须有 default
5. **参考示例**：完整示例见 `build/phase1/example-skill.SKILL.md`

---

## 3. 静态扫描：hermes-scan

### 3.1 功能

`hermes-scan.py` 是 SKILL.md v1.0 的静态合规分析器。它读取技能文件的 YAML frontmatter，执行三类验证，输出 A-F 评级。

### 3.2 使用方法

```bash
# 基础扫描
python3 hermes-scan.py my-skill.SKILL.md

# 美化输出
python3 hermes-scan.py --pretty my-skill.SKILL.md

# 人类可读摘要
python3 hermes-scan.py --summary my-skill.SKILL.md
```

### 3.3 输出格式

```json
{
  "skill_id": "devops/backup/git-auto-backup",
  "rating": "B",
  "score": 82,
  "findings": [
    {"severity": "warn", "category": "security", "message": "……"},
    {"severity": "error", "category": "contract", "message": "……"}
  ],
  "mandatory_check": {
    "present": ["skill_id", "version", "author", "description", "permissions", "cost", "input", "output"],
    "missing": []
  },
  "permission_analysis": {"scope_score": 18, "issues": ["……"]},
  "cost_analysis": {"declared": true, "issues": []}
}
```

### 3.4 评分标准

| 等级 | 分数 | 含义 |
|:----:|:----:|------|
| **A** | 90-100 | 全部必选字段 + 严格权限范围 + 完整契约 |
| **B** | 75-89 | 全部必选字段 + 轻微范围/可选字段缺失 |
| **C** | 55-74 | 全部必选字段但权限过于宽泛、cost 模糊 |
| **D** | 35-54 | 缺少 1-2 个必选字段 或 危险权限 |
| **E** | 15-34 | 缺少 3+ 必选字段、无 cost 声明 |
| **F** | 0-14 | 无法解析、无权限声明 |

### 3.5 常见扣分项

| 问题 | 扣分 | 修复方式 |
|------|:----:|---------|
| 缺失 `permissions` | -15 | 声明完整权限块 |
| 根级通配符 (`/**`) | -12 | 收缩到具体目录 |
| 网络域名为 `*` | -10 | 列出具体域名 |
| 缺失 `cost` 字段 | -10 | 添加 cost 声明 |
| 缺失 `token_estimate` | -6 | 声明 token 估算 |
| 缺失 output schema | -5 | 补充成功/失败输出结构 |

---

## 4. 审计回执：hermes-audit

### 4.1 功能

`hermes-audit.py` 将技能执行过程包装为可验证的审计回执（audit receipt）。它：
- 调用 `hermes-scan` 获取技能评级
- 执行外部命令并记录时间戳、退出码、输出
- 生成 SHA-256 签名，保证回执不可篡改

### 4.2 使用方法

```bash
# 基础用法
python3 hermes-audit.py --skill ./my-skill.SKILL.md --cmd "echo hello"

# 保存回执到文件
python3 hermes-audit.py --skill ./my-skill.SKILL.md --cmd "ls -la" --output receipt.json

# 美化输出
python3 hermes-audit.py --skill ./my-skill.SKILL.md --cmd "sleep 1" --pretty

# 跳过扫描（快速模式，评级默认 F）
python3 hermes-audit.py --skill ./my-skill.SKILL.md --cmd "date" --no-scan
```

### 4.3 回执结构

```json
{
  "receipt_id": "uuid4",
  "timestamp": "2026-05-14T11:43:00Z",
  "skill": {
    "skill_id": "devops/backup/git-auto-backup",
    "version": "1.0.0",
    "rating": "B",
    "score": 82,
    "declared_cost": { …… }
  },
  "execution": {
    "command": "echo hello",
    "started_at": "2026-05-14T11:43:00Z",
    "completed_at": "2026-05-14T11:43:00Z",
    "duration_ms": 12,
    "exit_code": 0,
    "status": "success"
  },
  "audit": {
    "input_hash": "sha256…",
    "output_summary": "hello",
    "token_cost": {
      "estimated_prompt_tokens": 2500,
      "estimated_completion_tokens": 1500,
      "estimated_total_tokens": 4000,
      "estimated_cost_usd": 0.008
    }
  },
  "signature": "sha256…"
}
```

### 4.4 验证回执

回执的 `signature` 字段是对回执其他所有字段的 canonical JSON 计算 SHA-256 得到。可以通过以下方式验证：

```python
import json, hashlib

receipt = json.load(open("receipt.json"))
sig = receipt.pop("signature")
canonical = json.dumps(receipt, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
assert sig == hashlib.sha256(canonical.encode()).hexdigest(), "回执已被篡改！"
```

---

## 5. Plugin Bridge：扩展系统

### 5.1 概述

Plugin Bridge (`hermes-plugin-bridge.py`) 是 Phase 4 的核心组件。它提供 **三个 Hook 点**，允许第三方开发者在技能执行的生命周期中插入自定义逻辑。

```
技能执行生命周期：

  ┌──────────┐     ┌───────────────┐     ┌───────────┐     ┌────────────┐
  │ 调用者    │────▶│ PRE_EXECUTION │────▶│  执行技能  │────▶│ POST_EXEC  │
  │ 提交参数  │     │ Hook (验证/修改)│     │ (命令执行) │     │ Hook (增强)│
  └──────────┘     └───────┬───────┘     └─────┬─────┘     └─────┬──────┘
                           │ 拒绝              │ 异常              │
                           ▼                   ▼                   │
                      ┌─────────┐        ┌───────────┐            │
                      │ 中止执行 │        │ ERROR Hook│◀───────────┘
                      └─────────┘        │ (告警/重试)│
                                         └─────┬─────┘
                                               │
                                        ┌──────▼──────┐
                                        │ abort/retry │
                                        │ /ignore     │
                                        └─────────────┘
```

### 5.2 快速开始

```python
from hermes_plugin_bridge import PluginBridge

# 创建桥接实例
bridge = PluginBridge()

# --- 注册 pre_execution handler ---
def my_validator(skill_meta, input_params):
    """检查 target_directory 是否存在"""
    import os
    target = input_params.get("target_directory", "")
    if target and not os.path.isdir(target):
        return {"allow": False, "reason": f"目录不存在: {target}"}
    return {"allow": True, "reason": "ok"}

bridge.register_pre_execution(my_validator, name="my.validator")

# --- 注册 post_execution handler ---
def my_logger(skill_meta, result, receipt):
    """将执行结果写入数据库"""
    # ... 写入数据库逻辑 ...
    return {"augmented": {"db_recorded": True}}

bridge.register_post_execution(my_logger, name="my.logger")

# --- 注册 error handler ---
def my_alerter(skill_meta, error_info):
    """发送告警到钉钉/飞书"""
    # ... 发送告警 ...
    return {"action": "abort", "reason": "已通知运维团队"}

bridge.register_error(my_alerter, name="my.alerter")

# --- 使用 ---
skill_meta = {"skill_id": "my-skill", "permissions": {"tools": ["terminal"]}}
params = {"target_directory": "/tmp"}

# Pre-execution
decision = bridge.pre_execution(skill_meta, params)
if not decision.allow:
    print(f"拒绝执行: {decision.reason}")
    exit(1)

# 执行技能（使用可能被修改的参数）
final_params = decision.modified_params
# ... 执行 ...

# Post-execution
result = {"status": "success", "exit_code": 0, "stdout": "OK", "duration_ms": 42}
augmented = bridge.post_execution(skill_meta, result)
```

### 5.3 通过配置文件注册

除了代码注册，Plugin Bridge 支持从 JSON 配置文件批量加载 handler：

```json
{
  "pre_execution": [
    {"name": "rate_limit", "handler": "myplugins.guards:rate_limit_check"},
    {"name": "scope_check", "handler": "myplugins.guards:validate_scope"}
  ],
  "post_execution": [
    {"name": "log_to_db", "handler": "myplugins.sinks:log_execution"}
  ],
  "error": [
    {"name": "pagerduty", "handler": "myplugins.alerts:page_on_call"}
  ]
}
```

加载配置：

```python
bridge = PluginBridge()
bridge.load_config("~/.hermes/plugins/config.json")
```

`handler` 字段使用 `module.path:function_name` 格式，Plugin Bridge 通过 `importlib` 动态加载。

---

## 6. 三个 Hook 详解

### 6.1 pre_execution Hook

**触发时机**：技能执行前，参数提交后。

**输入**：
| 参数 | 类型 | 说明 |
|------|------|------|
| `skill_metadata` | dict | 技能 frontmatter 元数据（skill_id, permissions, cost, …） |
| `input_params` | dict | 调用者提交的输入参数 |

**输出**：
| 字段 | 类型 | 说明 |
|------|------|------|
| `allow` | bool | 是否允许执行。`False` 会阻止执行并短路后续 handler |
| `reason` | str | 拒绝原因（`allow=False` 时必填） |
| `modified_params` | dict | 修改后的参数（可选，会合并到原始参数） |

**短路机制**：当任一 handler 返回 `allow=False` 时，后续 handler 不再执行，桥接立即返回拒绝决策。

**典型用途**：
- 参数校验（目录存在性、URL 合法性）
- 权限范围检查（技能声明的权限是否超出调用者授权）
- 速率限制（检查技能是否超过调用频率上限）
- 成本护栏（拦截 `api_cost_risk=CRITICAL` 的技能）
- 动态参数注入（添加默认值、注入环境变量）

**代码示例**：

```python
def rate_limit_handler(skill_meta, input_params):
    """速率限制：每技能每小时最多 10 次调用"""
    skill_id = skill_meta.get("skill_id", "unknown")
    current_hour_calls = redis.get(f"hermes:rate:{skill_id}:{datetime.now():%Y%m%d%H}")
    count = int(current_hour_calls or 0)

    if count >= 10:
        return {
            "allow": False,
            "reason": f"技能 {skill_id} 已达到每小时调用上限（10次）"
        }
    return {"allow": True, "reason": "ok"}

def param_injector(skill_meta, input_params):
    """自动注入 trace_id 到参数"""
    import uuid
    return {
        "allow": True,
        "reason": "ok",
        "modified_params": {"_trace_id": str(uuid.uuid4())}
    }
```

### 6.2 post_execution Hook

**触发时机**：技能执行完成后（无论成功或失败）。

**输入**：
| 参数 | 类型 | 说明 |
|------|------|------|
| `skill_metadata` | dict | 技能 frontmatter 元数据 |
| `execution_result` | dict | 执行结果（status, exit_code, stdout, stderr, duration_ms） |
| `audit_receipt` | dict | （可选）审计回执 |

**输出**：
| 字段 | 类型 | 说明 |
|------|------|------|
| `augmented` | dict | 增强数据，会合并到执行结果中 |

**特点**：所有 post_execution handler 都会执行，不会短路。

**典型用途**：
- 结果持久化（写入数据库、日志文件）
- 指标收集（执行耗时、成功率统计、Prometheus metrics）
- 通知推送（成功/失败通知到飞书、钉钉、Slack）
- 缓存更新（将技能输出写入缓存）
- 下游触发（根据结果触发关联技能）

**代码示例**：

```python
def metrics_collector(skill_meta, result, receipt):
    """收集执行指标到 Prometheus"""
    from prometheus_client import Counter, Histogram

    skill_id = skill_meta.get("skill_id", "unknown")
    status = result.get("status", "unknown")
    duration = result.get("duration_ms", 0)

    # 计数器
    skill_executions.labels(skill_id=skill_id, status=status).inc()
    # 直方图
    skill_duration.labels(skill_id=skill_id).observe(duration / 1000)

    return {"augmented": {"metrics_recorded": True}}

def slack_notifier(skill_meta, result, receipt):
    """失败时发送 Slack 通知"""
    if result.get("status") == "failure":
        requests.post(SLACK_WEBHOOK_URL, json={
            "text": f"❌ 技能 {skill_meta['skill_id']} 执行失败\n"
                    f"退出码: {result['exit_code']}\n"
                    f"错误: {result.get('stderr', '')[:200]}"
        })
    return {"augmented": {"notified": True}}
```

### 6.3 error Hook

**触发时机**：技能执行过程中抛出未处理的异常时。

**输入**：
| 参数 | 类型 | 说明 |
|------|------|------|
| `skill_metadata` | dict | 技能 frontmatter 元数据 |
| `error_info` | dict | 错误信息（error_type, error_message, traceback, skill_id, input_params） |

**输出**：
| 字段 | 类型 | 说明 |
|------|------|------|
| `action` | str | 处理动作：`retry`（重试）、`abort`（中止）、`ignore`（忽略） |
| `reason` | str | 动作原因说明 |

**链式处理**：Error handler 按注册顺序执行，后续 handler 可以看到前一个 handler 的 action 并覆盖。若任一 handler 返回 `ignore`，链提前终止。

**典型用途**：
- 告警推送（PagerDuty、飞书、钉钉）
- 自动重试判断（网络超时→retry，权限错误→abort）
- 清理资源（删除临时文件、释放锁）
- 降级处理（切换到备用服务）

**代码示例**：

```python
def pagerduty_alerter(skill_meta, error_info):
    """严重错误触发 PagerDuty 告警"""
    if error_info.get("error_type") in ("FatalError", "SystemError"):
        requests.post(PAGERDUTY_URL, json={
            "severity": "critical",
            "summary": f"Hermes skill {skill_meta['skill_id']} failed",
            "detail": error_info.get("error_message", "")
        })
    return {"action": "abort", "reason": "严重错误，已触发 on-call 告警"}

def retry_decider(skill_meta, error_info):
    """基于错误类型决定是否重试"""
    msg = error_info.get("error_message", "").lower()
    if any(kw in msg for kw in ("timeout", "connection reset", "429", "temporary")):
        return {"action": "retry", "reason": "检测到瞬时错误，建议重试"}
    return {"action": "abort", "reason": "非瞬时错误，中止执行"}

def cleanup_on_error(skill_meta, error_info):
    """错误时清理临时文件"""
    import shutil
    tmp_dir = f"/tmp/hermes-{skill_meta.get('skill_id', 'unknown')}"
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    return {"action": "abort", "reason": "已清理临时资源"}
```

---

## 7. 部署与配置

### 7.1 文件位置

```
~/.hermes/
├── workspace/
│   └── build/
│       ├── phase1/                       # SKILL.md v1.0 格式规范 + 示例
│       │   ├── SKILL.md.v1.spec.md
│       │   └── example-skill.SKILL.md
│       ├── phase2/                       # 静态扫描器
│       │   └── hermes-scan.py
│       ├── phase3/                       # 审计回执
│       │   └── hermes-audit.py
│       └── phase4/                       # Plugin Bridge + 扩展指南
│           ├── hermes-plugin-bridge.py   # ← 核心模块
│           ├── plugin-config.example.json
│           └── EXTENSION-GUIDE.md        # ← 本文档
├── plugins/
│   ├── config.json                       # 你的插件配置
│   ├── guards.py                         # pre_execution handlers
│   ├── sinks.py                          # post_execution handlers
│   └── alerts.py                         # error handlers
└── skills/
    └── *.SKILL.md                        # 你的技能文件
```

### 7.2 安装依赖

```bash
pip install pyyaml   # hermes-scan 和 hermes-audit 的依赖
```

Plugin Bridge 仅依赖 Python 标准库（`importlib`、`json`、`logging`、`pathlib`），无需额外安装。

### 7.3 创建自定义插件

**步骤 1**：创建 handler 模块

```python
# ~/.hermes/plugins/guards.py

def validate_api_key(skill_metadata, input_params):
    """验证 API Key 是否有效"""
    api_key = input_params.get("api_key", "")
    if not api_key or len(api_key) < 16:
        return {"allow": False, "reason": "API Key 无效或过短"}
    return {"allow": True, "reason": "ok"}
```

**步骤 2**：编写配置文件

```json
{
  "pre_execution": [
    {"name": "api_key_check", "handler": "plugins.guards:validate_api_key"}
  ]
}
```

**步骤 3**：在代码中加载

```python
import sys
sys.path.insert(0, str(Path.home() / ".hermes"))
# 现在 'plugins.guards' 可以被 importlib 找到

from hermes_plugin_bridge import PluginBridge
bridge = PluginBridge()
bridge.load_config("~/.hermes/plugins/config.json")
```

### 7.4 与 hermes-audit 集成

将 Plugin Bridge 嵌入审计流程：

```python
from hermes_plugin_bridge import create_default_bridge
from hermes_audit import …  # Phase 3 模块

bridge = create_default_bridge()

def execute_with_bridge(skill_path, command, input_params):
    # 1. 解析技能元数据
    fm, body = parse_skill_frontmatter(skill_path)

    # 2. Pre-execution
    decision = bridge.pre_execution(fm, input_params)
    if not decision.allow:
        raise RuntimeError(f"Pre-execution rejected: {decision.reason}")

    # 3. 执行
    try:
        result = run_command(command)  # 你的执行逻辑
    except Exception as e:
        error_info = {"error_type": type(e).__name__, "error_message": str(e), …}
        action = bridge.error(fm, error_info)
        if action.action == "retry":
            result = run_command(command)  # 重试
        else:
            raise

    # 4. Post-execution
    receipt = build_receipt(fm, result, …)
    augmented = bridge.post_execution(fm, result, receipt)

    return result, receipt, augmented
```

---

## 8. 最佳实践

### 8.1 权限范围最小化

```yaml
# ❌ 坏：根级通配符
permissions:
  filesystem:
    read: ["/**"]
    write: ["/**"]

# ✅ 好：精确路径
permissions:
  filesystem:
    read: ["~/.hermes/config.yaml", "~/.hermes/workspace/*.md"]
    write: ["~/.hermes/logs/"]
```

### 8.2 成本估算诚实化

```yaml
# ❌ 坏：成本估算为 0，但实际调用外部 API
cost:
  token_estimate:
    base: 0
    per_run: {input: 0, output: 0, total: 0}
  api_cost_risk: LOW

# ✅ 好：诚实估算
cost:
  token_estimate:
    base: 600
    per_run: {input: 2500, output: 1500, total: 4000}
  api_cost_risk: MEDIUM
```

### 8.3 Handler 设计原则

| 原则 | 说明 |
|------|------|
| **幂等性** | 同一个 handler 重复执行应产生相同结果 |
| **无副作用** | pre_execution handler 不应修改外部状态（仅验证和参数修改） |
| **快速失败** | 验证失败应立即返回，不执行耗时操作 |
| **异常安全** | handler 内部异常不应导致整个链崩溃（Plugin Bridge 会捕获并记录） |
| **命名规范** | 使用 `namespace.name` 格式命名 handler，如 `myorg.guards.rate_limit` |

### 8.4 测试策略

```python
# 单元测试 Handler
def test_my_validator():
    result = my_validator(
        {"skill_id": "test", "permissions": {"tools": ["terminal"]}},
        {"target_directory": "/tmp"}
    )
    assert result["allow"] is True

# 集成测试 Bridge
def test_bridge_chain():
    bridge = PluginBridge()
    bridge.register_pre_execution(handler1, name="h1")
    bridge.register_pre_execution(handler2, name="h2")

    # 模拟执行流
    decision = bridge.pre_execution(skill_meta, params)
    assert decision.allow

    result = bridge.post_execution(skill_meta, exec_result, receipt)
    assert "logged" in result.augmented
```

### 8.5 安全注意事项

1. **配置文件权限**：`~/.hermes/plugins/config.json` 应设为 `600`（仅所有者可读写），防止未授权修改
2. **handler 来源验证**：仅加载可信来源的 handler 模块，避免 `importlib` 加载恶意代码
3. **日志脱敏**：post_execution 日志中避免记录凭据、Token 等敏感信息
4. **重试上限**：error handler 的 `retry` 应配合最大重试次数，防止无限重试循环
5. **超时保护**：每个 handler 应有隐式或显式的超时机制

### 8.6 版本兼容

| Hermes 平台版本 | SKILL.md 格式 | hermes-scan | Plugin Bridge |
|:--------------:|:------------:|:-----------:|:-------------:|
| v1.0.0 | v1.0 | ✅ | ✅ |

当 SKILL.md 格式升级到 v2.0 时，Plugin Bridge 的 handler 签名将保持不变（向后兼容），但 `skill_metadata` 内容可能增加新字段。

---

## 9. 附录

### 9.1 完整技能示例

参见 `build/phase1/example-skill.SKILL.md` — 一个符合 v1.0 规范的备份技能。

### 9.2 Plugin Bridge 内置 Handler

Bridge 模块提供了 4 个内置 handler，展示 handler 契约：

| Handler | Hook | 功能 |
|---------|------|------|
| `builtin_permission_check` | pre_execution | 拒绝 tools 为空的技能 |
| `builtin_cost_guard` | pre_execution | 拦截 api_cost_risk=CRITICAL 的技能 |
| `builtin_log_execution` | post_execution | 将执行摘要输出到 stderr |
| `builtin_alert_on_error` | error | 检测瞬时错误（timeout/network），建议 retry |

可通过 `create_default_bridge()` 一键创建预装内置 handler 的 Bridge 实例。

### 9.3 常用资源

| 资源 | 路径 |
|------|------|
| 格式规范 | `build/phase1/SKILL.md.v1.spec.md` |
| 示例技能 | `build/phase1/example-skill.SKILL.md` |
| 扫描器源码 | `build/phase2/hermes-scan.py` |
| 审计器源码 | `build/phase3/hermes-audit.py` |
| Plugin Bridge 源码 | `build/phase4/hermes-plugin-bridge.py` |
| 示例配置 | `build/phase4/plugin-config.example.json` |

### 9.4 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|------|------|---------|------|
| 1.0.0 | 2026-05-14 | 初始版本，Plugin Bridge v1 + 扩展指南 | team_build |

---

> **本指南面向所有 Hermes 平台开发者。如有疑问或建议，请联系 team_build（技术开发·工匠长）。**
