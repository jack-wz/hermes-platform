# SKILL.md v1.0 格式规范

> **Hermes 平台技能格式宪章**
>
> 版本：1.0.0
> 生效日期：2026-05-14
> 维护者：team_build（技术开发·工匠长）
> 适用范围：所有 Hermes 平台技能文件（SKILL.md）

---

## 一、总则

### 1.1 目的

SKILL.md 是 Hermes 平台上每一个可复用技能的**唯一真相源**（single source of truth）。本规范定义了 SKILL.md v1.0 的文件格式、必选字段、可选字段和验证规则，确保所有技能在安全声明、成本估算、输入输出契约等方面具备一致性和可审计性。

### 1.2 设计原则

1. **兼容优先**：向前兼容现有 Hermes SKILL.md 格式（YAML frontmatter + Markdown body）
2. **最小必须原则**：必选字段只包含安全和审计所必需的信息，不为"完整"而增加无意义负担
3. **机器可读**：所有必选字段必须能被自动化工具（如 `hermes scan`）精确解析
4. **人类可写**：格式足够简单，技能作者无需专门工具即可编写
5. **渐进增强**：可选字段为高级场景预留，不影响基本可用性

### 1.3 文件结构

一个合法的 SKILL.md v1.0 文件由两部分组成：

```
---
(YAML frontmatter — 必选字段 + 可选字段)
---

(Markdown body — 技能指令与实现)
```

- **Frontmatter**：使用 `---` 分隔符包裹的 YAML 块，包含所有元数据
- **Body**：标准 Markdown 格式的技能实现内容，可使用任何合法的 Markdown 语法

---

## 二、必选字段

以下字段在任意 SKILL.md v1.0 文件中**必须存在且不能为空**。

### 2.1 `skill_id`

| 属性 | 说明 |
|------|------|
| **类型** | `string` |
| **格式** | `{domain}/{category}/{name}` 或 `{namespace}/{name}` |
| **约束** | 全局唯一，小写字母、数字、连字符，最长 128 字符 |
| **示例** | `devops/backup/git-auto-backup` |

`skill_id` 是技能的全局唯一标识符。推荐使用三段式命名：`领域/类别/名称`，以便于分类和检索。已发布的 `skill_id` 不可更改（变更视为新技能）。

### 2.2 `version`

| 属性 | 说明 |
|------|------|
| **类型** | `string` |
| **格式** | 语义化版本（SemVer）：`MAJOR.MINOR.PATCH` |
| **约束** | MAJOR ≥ 1（0.x 版本视为开发中，不适用于生产） |
| **示例** | `1.0.0` |

`version` 遵循 [Semantic Versioning 2.0.0](https://semver.org/lang/zh-CN/)。当权限声明、成本模式、输入输出契约发生不兼容变更时，必须递增 MAJOR 版本。

### 2.3 `author`

| 属性 | 说明 |
|------|------|
| **类型** | `string` 或 `object` |
| **格式** | 字符串形式：`名称 <email>`；对象形式见下方 |
| **约束** | 必须包含可追溯的责任人信息 |
| **示例** | `"龙虾总控·司令台 <main@hermes.internal>"` |

对象形式（推荐用于团队技能）：

```yaml
author:
  name: "team_build"
  display: "技术开发·工匠长"
  contact: "build@hermes.internal"
```

### 2.4 `description`

| 属性 | 说明 |
|------|------|
| **类型** | `string` |
| **格式** | 单行或多行字符串（YAML `|` 或 `>`） |
| **约束** | 最短 20 字符，最长 500 字符 |
| **示例** | `"自动备份指定目录到远程 Git 仓库，支持增量提交、定时触发和冲突检测"` |

`description` 必须清晰说明：该技能**做什么**（功能）和**何时使用**（触发条件）。禁止使用"一个关于...的工具"等空洞描述。

### 2.5 `permissions`（权限/安全声明）

| 属性 | 说明 |
|------|------|
| **类型** | `object` |
| **约束** | 必须至少声明一个权限维度；所有权限声明必须精确到路径或域名级别 |

`permissions` 描述了技能运行时所需的系统访问权限。**这是安全审计的核心字段**，不允许使用通配符（`*`）或模糊声明（如"访问文件系统"）。

```yaml
permissions:
  # 文件系统访问（可选，但若技能读写文件则必须声明）
  filesystem:
    read:                          # 读权限 — 精确到目录或文件
      - "~/.hermes/config.yaml"
      - "/tmp/hermes-*"
    write:                         # 写权限 — 精确到目录或文件
      - "~/.hermes/backups/"
      
  # 网络访问（可选，但若技能发起网络请求则必须声明）
  network:
    domains:                       # 允许访问的域名
      - "api.github.com"
      - "raw.githubusercontent.com"
    ports: [443]                   # 允许访问的端口
    protocols: ["https"]           # 允许的协议
    
  # 工具依赖（必须声明：技能运行时需要哪些 Hermes 工具集）
  tools:
    - "terminal"                   # 需要 Shell 执行能力
    - "file"                       # 需要文件读写能力
    
  # 凭据要求（必须声明：技能需要哪些外部凭据/密钥）
  credentials:
    - name: "GITHUB_TOKEN"
      type: "env"
      scope: "repo"                # 凭据权限范围
      required: true
```

**权限声明规则**：
- 若技能不访问文件系统，`filesystem` 可省略或设置为 `read: []` / `write: []`
- 若技能不发起网络请求，`network` 可省略
- `tools` 至少包含一项
- `credentials` 若无需外部凭据，必须显式声明为空数组 `[]`

### 2.6 `cost`（成本/用量模式）

| 属性 | 说明 |
|------|------|
| **类型** | `object` |
| **约束** | 必须包含 `token_estimate` 和 `api_cost_risk` |

`cost` 字段帮助调度系统（`hermes run --audit`）在运行前评估技能的资源消耗，并生成代理收据中的成本归属。

```yaml
cost:
  # Token 估算（必选）
  token_estimate:
    base: 500                     # 技能自身文档消耗的 token 数
    per_run:                      # 每次调用的预估 token 消耗
      input: 2000                 # 输入 token 估算（prompt + context）
      output: 1000                # 输出 token 估算（skill response）
      total: 3000                 # 每次调用总 token 估算
    
  # API 成本风险等级（必选）
  api_cost_risk: "LOW"           # LOW | MEDIUM | HIGH | CRITICAL
  
  # 速率限制（可选但推荐）
  rate_limits:
    max_calls_per_hour: 10
    max_calls_per_day: 50
    retry_strategy: "exponential_backoff"   # 重试策略
```

**`api_cost_risk` 等级定义**：

| 等级 | 含义 | 判定标准 | 示例 |
|------|------|---------|------|
| `LOW` | 几乎无外部 API 成本 | 不使用或极少使用免费/本地 API | 纯文件操作技能 |
| `MEDIUM` | 有可预测的外部 API 成本 | 每次调用 $0.001-$0.05 | GitHub API 调用 |
| `HIGH` | 有显著的外部 API 成本 | 每次调用 $0.05-$0.50 | 调用 GPT-4 作为子步骤 |
| `CRITICAL` | 每次调用成本不可预测或极高 | 每次调用 >$0.50 或依赖昂贵外部服务 | 大规模 web scraping + AI 分析 |

### 2.7 `input`（输入契约）

| 属性 | 说明 |
|------|------|
| **类型** | `object` |
| **约束** | 必须声明所有输入参数及其类型、是否必选、默认值 |

```yaml
input:
  required:                       # 必选输入
    - name: "target_directory"
      type: "string"              # string | number | boolean | array | object
      description: "需要备份的目标目录（绝对路径）"
      validation: "^/.*"          # 可选：正则校验
      
    - name: "remote_url"
      type: "string"
      description: "远程 Git 仓库地址"
      validation: "^https://github.com/.*"
      
  optional:                       # 可选输入
    - name: "commit_message"
      type: "string"
      description: "自定义提交信息"
      default: "auto-backup: {{timestamp}}"
      
    - name: "branch"
      type: "string"
      description: "目标分支名"
      default: "main"
```

**输入契约规则**：
- `required` 为空时，技能视为"无参数触发"
- 每个参数的 `type` 必须声明
- 可选参数必须提供 `default` 值
- `validation` 使用 JavaScript 兼容的正则表达式字符串

### 2.8 `output`（输出契约）

| 属性 | 说明 |
|------|------|
| **类型** | `object` |
| **约束** | 必须声明成功输出和失败输出的结构 |

```yaml
output:
  success:
    description: "备份成功完成"
    schema:                       # 输出结构（JSON Schema-like）
      backup_id: "string"
      commit_hash: "string"
      files_backed_up: "number"
      timestamp: "string (ISO 8601)"
      
  failure:
    description: "备份失败"
    schema:
      error_code: "string"        # 错误码
      error_message: "string"     # 错误描述
      recoverable: "boolean"      # 是否可重试
```

**输出契约规则**：
- `success` 必须声明
- `failure` 必须声明
- `schema` 中的每个字段需附带类型注释
- 若输出为文件，需声明文件路径和格式

---

## 三、可选字段

以下字段为可选，但强烈建议在适当场景下填写。

### 3.1 `tags`

```yaml
tags:
  - "backup"
  - "git"
  - "automation"
  - "devops"
```

用于技能分类和搜索。建议使用小写英文标签，数量不超过 8 个。

### 3.2 `dependencies`

```yaml
dependencies:
  skills:                         # 依赖的其他技能
    - "devops/reference-source-mirror-sync"
  packages:                       # 依赖的系统包
    - name: "git"
      version: ">=2.30"
      install_hint: "apt-get install git"
```

声明技能运行所需的外部依赖。`packages` 中应包含安装提示。

### 3.3 `environment_vars`

```yaml
environment_vars:
  - name: "HERMES_BACKUP_DIR"
    description: "备份根目录（覆盖默认路径）"
    default: "~/.hermes/backups"
    required: false
```

声明技能识别但非凭据的环境变量（凭据类请放入 `permissions.credentials`）。

### 3.4 `credential_requirements`

```yaml
credential_requirements:
  storage: "keychain"             # keychain | env_file | vault | manual
  rotation_days: 90               # 建议轮换周期（天）
  validation_method: "curl -H 'Authorization: token $GITHUB_TOKEN' https://api.github.com/user"
```

更详细的凭据管理说明，用于安全审计。当 `permissions.credentials` 不足以描述凭据需求时使用。

### 3.5 `pitfalls`

```yaml
pitfalls:
  - "目标目录不存在时不会自动创建，调用方必须预检查"
  - "大文件（>100MB）备份可能触发 Git LFS 限制"
  - "并发备份同一目录可能产生合并冲突"
  - "GitHub Token 过期后错误信息不明确，需检查 HTTP 401"
```

记录已知的陷阱、常见错误和注意事项。每条应简洁、可操作。

### 3.6 `metadata`

```yaml
metadata:
  hermes:
    emoji: "💾"                   # 在 UI 中显示的图标
    tags: ["backup", "git"]       # 可被 Hermes 原生命名空间读取的标签
    always: false                 # 是否在每次 session 中自动加载
    related_skills:               # 关联技能
      - "devops/reference-source-mirror-sync"
```

与现有 Hermes 生态兼容的元数据块。保留自现有格式，向后兼容。

---

## 四、验证规则

### 4.1 结构验证

| 检查项 | 规则 |
|--------|------|
| 文件存在 | 文件路径必须为 `**/SKILL.md` |
| Frontmatter 合法性 | 必须能被 YAML 1.2 解析器正确解析 |
| 必选字段完整性 | 8 个必选字段（2.1-2.8）必须全部存在且非空 |
| `skill_id` 唯一性 | 在技能目录中全局唯一 |
| `version` 格式 | 必须符合 SemVer 正则：`^\d+\.\d+\.\d+$` |

### 4.2 安全验证

| 检查项 | 规则 |
|--------|------|
| 无通配符权限 | `filesystem` 和 `network.domains` 中不允许 `*` |
| 凭据声明完整 | `credentials` 中每个条目必须有 `name`, `type`, `scope` |
| 工具声明完整 | `tools` 中每个条目必须是已知的 Hermes 工具集名称 |
| API 风险等级合法 | `api_cost_risk` 必须是 `LOW|MEDIUM|HIGH|CRITICAL` |

### 4.3 契约验证

| 检查项 | 规则 |
|--------|------|
| 输入类型合法 | `input` 中每个参数的 `type` 必须是合法类型 |
| 必选参数有描述 | `input.required` 中每个参数必须有 `description` |
| 可选参数有默认值 | `input.optional` 中每个参数必须有 `default` |
| 输出 schema 完整 | `output.success` 和 `output.failure` 必须都包含 `schema` |

---

## 五、版本迁移

### 5.1 从旧格式迁移

现有 Hermes SKILL.md 文件（仅含 `name`, `description`, `version`, `metadata` 等）可通过以下步骤迁移到 v1.0：

1. 将 `name` 映射为 `skill_id`（按三段式命名规范调整）
2. 添加 `author` 字段（从现有 metadata 或 git blame 推断）
3. 添加 `permissions` 块（分析技能 body 中的工具和路径使用）
4. 添加 `cost` 块（基于技能复杂度估算）
5. 添加 `input` 和 `output` 块（从技能 body 中的参数约定提取）
6. 可选字段按需补充

### 5.2 向后兼容

Hermes 运行时应在加载 SKILL.md 时检测格式版本：
- 若存在 `skill_id` 字段 → v1.0 格式，启用完整审计
- 若仅有 `name` 字段 → 旧格式，按宽松模式运行，在日志中记录"建议升级"

---

## 六、附录

### 6.1 完整示例

参见同级目录下的 `example-skill.SKILL.md` 文件。

### 6.2 字段速查表

| 字段 | 类型 | 必选 | 章节 |
|------|------|:----:|------|
| `skill_id` | string | ✅ | 2.1 |
| `version` | string | ✅ | 2.2 |
| `author` | string/object | ✅ | 2.3 |
| `description` | string | ✅ | 2.4 |
| `permissions` | object | ✅ | 2.5 |
| `cost` | object | ✅ | 2.6 |
| `input` | object | ✅ | 2.7 |
| `output` | object | ✅ | 2.8 |
| `tags` | array | 可选 | 3.1 |
| `dependencies` | object | 可选 | 3.2 |
| `environment_vars` | array | 可选 | 3.3 |
| `credential_requirements` | object | 可选 | 3.4 |
| `pitfalls` | array | 可选 | 3.5 |
| `metadata` | object | 可选 | 3.6 |

### 6.3 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|------|------|---------|------|
| 1.0.0 | 2026-05-14 | 初始版本，定义完整 v1.0 格式规范 | team_build |

---

> **本文件为 Hermes 平台技能格式的规范性文档。所有提交至 Hermes 技能仓库的技能必须通过 `hermes scan` 的 v1.0 合规检查。**
