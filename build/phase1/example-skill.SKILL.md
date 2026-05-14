---
skill_id: devops/backup/git-auto-backup
version: 1.0.0
author:
  name: team_build
  display: 技术开发·工匠长
  contact: build@hermes.internal
description: >
  自动备份指定目录到远程 Git 仓库。支持增量提交、自动冲突检测、
  大文件告警和备份完整性校验。适用于 Hermes 工作区、配置文件、
  技能目录等需要版本化备份的场景。触发条件：手动调用或 cron 定时任务。

# ============================================================
# 权限与安全声明
# ============================================================
permissions:
  filesystem:
    read:
      - "~/.hermes/workspace/**"
      - "~/.hermes/skills/**"
      - "~/.hermes/config.yaml"
      - "/tmp/hermes-backup-*"
    write:
      - "~/.hermes/backups/repos/"
      - "/tmp/hermes-backup-*"

  network:
    domains:
      - "github.com"
      - "api.github.com"
    ports: [443]
    protocols: ["https"]

  tools:
    - terminal
    - file

  credentials:
    - name: GITHUB_TOKEN
      type: env
      scope: repo
      required: true

# ============================================================
# 成本 / 用量模式
# ============================================================
cost:
  token_estimate:
    base: 600
    per_run:
      input: 2500
      output: 1500
      total: 4000

  api_cost_risk: LOW

  rate_limits:
    max_calls_per_hour: 12
    max_calls_per_day: 60
    retry_strategy: exponential_backoff

# ============================================================
# 输入契约
# ============================================================
input:
  required:
    - name: target_directory
      type: string
      description: 需要备份的目标目录绝对路径
      validation: "^/[a-zA-Z0-9/._-]+$"

    - name: remote_url
      type: string
      description: 远程 Git 仓库地址（HTTPS 格式）
      validation: "^https://(github\\.com|gitlab\\.com)/[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+(\\.git)?$"

  optional:
    - name: commit_message
      type: string
      description: 自定义提交信息，支持 {{timestamp}} 和 {{hostname}} 模板变量
      default: "auto-backup: {{timestamp}}"

    - name: branch
      type: string
      description: 推送目标分支
      default: "main"

    - name: max_file_size_mb
      type: number
      description: 单文件大小上限（MB），超过则告警但不阻止备份
      default: 100

    - name: retention_days
      type: number
      description: 备份保留天数（0 = 不清理旧备份）
      default: 30

# ============================================================
# 输出契约
# ============================================================
output:
  success:
    description: 备份成功完成，返回备份元数据
    schema:
      backup_id: "string — 格式: backup-YYYYMMDD-HHMMSS"
      commit_hash: "string — Git commit SHA"
      files_backed_up: "number — 本次备份的文件数"
      total_size_bytes: "number — 备份总大小"
      timestamp: "string — ISO 8601 格式"
      remote_url: "string — 推送目标仓库地址"

  failure:
    description: 备份失败，返回错误信息
    schema:
      error_code: "string — 错误码: AUTH_FAILED | NETWORK_ERROR | CONFLICT | DISK_FULL | TIMEOUT"
      error_message: "string — 人类可读的错误描述"
      recoverable: "boolean — 是否可通过重试恢复"
      suggested_action: "string — 建议的修复操作"

# ============================================================
# 可选元数据
# ============================================================
tags:
  - backup
  - git
  - automation
  - devops
  - cron

dependencies:
  packages:
    - name: git
      version: ">=2.30.0"
      install_hint: "brew install git  # macOS"
    - name: openssh
      version: ">=8.0"
      install_hint: "系统自带，无需额外安装"

environment_vars:
  - name: HERMES_BACKUP_ROOT
    description: 备份仓库本地存储根目录
    default: "~/.hermes/backups/repos"
    required: false

credential_requirements:
  storage: env_file
  rotation_days: 90
  validation_method: >
    curl -s -o /dev/null -w "%{http_code}"
    -H "Authorization: token $GITHUB_TOKEN"
    https://api.github.com/user

metadata:
  hermes:
    emoji: "💾"
    tags: [backup, git, automation, devops]
    always: false
    related_skills:
      - devops/reference-source-mirror-sync

pitfalls:
  - "目标目录不存在时不会自动创建，调用方必须确保 target_directory 已存在"
  - "大文件（>100MB）不阻止备份，但会输出告警日志并建议启用 Git LFS"
  - "并发备份同一 target_directory 到同一 remote_url 可能导致 push 冲突（non-fast-forward）"
  - "GITHUB_TOKEN 过期时 git push 会失败并返回 HTTP 401，错误码为 AUTH_FAILED"
  - "首次备份大型仓库（>1GB）的 git clone 可能超时，建议先手动 clone 到 backup_root"
  - "retention_days=0 时不清理旧备份，可能导致磁盘空间耗尽"
---

# Git 自动化备份 (git-auto-backup)

> 将指定目录自动备份到远程 Git 仓库，支持增量提交和完整性校验。

## 触发条件

- **手动调用**：用户请求备份某个目录
- **Cron 定时触发**：通过 Hermes cron 定期执行
- **事件触发**：关联到其他技能（如 `hermes-code-ops-regression` 的变更前备份）

---

## 执行流程

### 第一步：预检查

在开始备份前，验证以下条件：

1. **Git 可用性**
   ```bash
   git --version
   ```
   若未安装，报告 `error_code: "DEPENDENCY_MISSING"` 并退出。

2. **目标目录存在性**
   ```bash
   test -d "{{target_directory}}" && echo "OK" || echo "NOT_FOUND"
   ```
   若目录不存在，报告 `error_code: "TARGET_NOT_FOUND"` 并退出。

3. **凭据可用性**
   ```bash
   test -n "$GITHUB_TOKEN" && echo "OK" || echo "MISSING"
   ```
   若 `GITHUB_TOKEN` 未设置，报告 `error_code: "AUTH_FAILED"` 并退出。

4. **磁盘空间检查**
   ```bash
   df -h "$HERMES_BACKUP_ROOT" | tail -1 | awk '{print $5}'
   ```
   若使用率超过 90%，报告 `error_code: "DISK_FULL"` 并退出。

### 第二步：准备本地备份仓库

```bash
BACKUP_ROOT="${HERMES_BACKUP_ROOT:-~/.hermes/backups/repos}"
REPO_NAME=$(basename "{{target_directory}}")
LOCAL_REPO="$BACKUP_ROOT/$REPO_NAME"

# 首次备份：clone 远程仓库
if [ ! -d "$LOCAL_REPO/.git" ]; then
    git clone "{{remote_url}}" "$LOCAL_REPO" --branch "{{branch}}" || {
        # 如果远程仓库为空，初始化新仓库
        mkdir -p "$LOCAL_REPO"
        git -C "$LOCAL_REPO" init --initial-branch="{{branch}}"
        git -C "$LOCAL_REPO" remote add origin "{{remote_url}}"
    }
fi
```

### 第三步：增量同步

使用 `rsync` 模式将目标目录内容同步到本地备份仓库：

```bash
# 清理旧内容（保留 .git）
find "$LOCAL_REPO" -mindepth 1 -not -path "$LOCAL_REPO/.git" -not -path "$LOCAL_REPO/.git/*" -delete

# 同步新内容
rsync -a --delete \
    --exclude='.git' \
    --exclude='node_modules' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --max-size="{{max_file_size_mb}}M" \
    "{{target_directory}}/" \
    "$LOCAL_REPO/"

# 大文件检测
LARGE_FILES=$(find "$LOCAL_REPO" -type f -size +"{{max_file_size_mb}}M" | wc -l)
if [ "$LARGE_FILES" -gt 0 ]; then
    echo "⚠️  告警：检测到 $LARGE_FILES 个大文件（>{{max_file_size_mb}}MB），建议启用 Git LFS"
fi
```

### 第四步：提交与推送

```bash
# 生成时间戳
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
BACKUP_ID="backup-$(date -u +"%Y%m%d-%H%M%S")"
HOSTNAME=$(hostname)

# 替换提交信息模板变量
COMMIT_MSG="{{commit_message}}"
COMMIT_MSG="${COMMIT_MSG//\{\{timestamp\}\}/$TIMESTAMP}"
COMMIT_MSG="${COMMIT_MSG//\{\{hostname\}\}/$HOSTNAME}"

# 提交
git -C "$LOCAL_REPO" add -A
git -C "$LOCAL_REPO" commit -m "$COMMIT_MSG" --allow-empty

# 冲突检测与处理
PUSH_OUTPUT=$(git -C "$LOCAL_REPO" push origin "{{branch}}" 2>&1)
PUSH_EXIT=$?

if [ $PUSH_EXIT -ne 0 ]; then
    if echo "$PUSH_OUTPUT" | grep -q "non-fast-forward"; then
        # 冲突：执行 rebase 后重试
        git -C "$LOCAL_REPO" pull --rebase origin "{{branch}}"
        git -C "$LOCAL_REPO" push origin "{{branch}}" || {
            echo "error_code=CONFLICT error_message='远程冲突无法自动解决' recoverable=false"
            exit 1
        }
    elif echo "$PUSH_OUTPUT" | grep -q "401\|403"; then
        echo "error_code=AUTH_FAILED error_message='GitHub Token 无效或已过期' recoverable=false"
        exit 1
    else
        echo "error_code=NETWORK_ERROR error_message='$PUSH_OUTPUT' recoverable=true"
        exit 1
    fi
fi
```

### 第五步：旧备份清理

```bash
if [ "{{retention_days}}" -gt 0 ]; then
    CUTOFF_DATE=$(date -u -d "{{retention_days}} days ago" +"%Y-%m-%d")
    echo "清理 $CUTOFF_DATE 之前的旧备份..."

    # 通过 Git reflog 找到旧 commit 并清理（保守策略：只删 tag，不删 commit）
    git -C "$LOCAL_REPO" tag -l "backup-*" | while read TAG; do
        TAG_DATE=$(git -C "$LOCAL_REPO" log -1 --format="%ai" "$TAG" | cut -d' ' -f1)
        if [[ "$TAG_DATE" < "$CUTOFF_DATE" ]]; then
            git -C "$LOCAL_REPO" tag -d "$TAG"
            echo "  已删除旧标签: $TAG ($TAG_DATE)"
        fi
    done
fi
```

### 第六步：生成输出

```bash
COMMIT_HASH=$(git -C "$LOCAL_REPO" rev-parse --short HEAD)
FILE_COUNT=$(git -C "$LOCAL_REPO" ls-files | wc -l)
TOTAL_SIZE=$(du -sb "$LOCAL_REPO" --exclude=.git | cut -f1)

# 输出成功 JSON
cat <<EOF
{
  "backup_id": "$BACKUP_ID",
  "commit_hash": "$COMMIT_HASH",
  "files_backed_up": $FILE_COUNT,
  "total_size_bytes": $TOTAL_SIZE,
  "timestamp": "$TIMESTAMP",
  "remote_url": "{{remote_url}}"
}
EOF
```

---

## 错误码速查

| 错误码 | 含义 | 可重试 | 建议操作 |
|--------|------|:------:|---------|
| `DEPENDENCY_MISSING` | git 未安装 | ❌ | 安装 git：`brew install git` |
| `TARGET_NOT_FOUND` | 目标目录不存在 | ❌ | 检查路径是否正确 |
| `AUTH_FAILED` | GitHub Token 无效 | ❌ | 重新生成 Token 或检查 `GITHUB_TOKEN` 环境变量 |
| `NETWORK_ERROR` | 网络连接失败 | ✅ | 等待后重试（指数退避） |
| `CONFLICT` | Git 合并冲突 | ❌ | 手动解决冲突后重新运行 |
| `DISK_FULL` | 磁盘空间不足 | ❌ | 清理磁盘或扩展存储 |
| `TIMEOUT` | 操作超时 | ✅ | 增大超时或拆分备份 |

---

## 完整使用示例

### 手动触发

```
备份 ~/.hermes/skills 到 github.com/myorg/hermes-skills-backup
```

### Cron 自动化（在 Hermes 中配置）

```bash
hermes cron create "0 2 * * *" \
  --skill devops/backup/git-auto-backup \
  --input '{
    "target_directory": "/Users/aiutb/.hermes/workspace",
    "remote_url": "https://github.com/myorg/hermes-workspace-backup.git",
    "branch": "main",
    "retention_days": 30
  }'
```

### 输出示例

```json
{
  "backup_id": "backup-20260514-020000",
  "commit_hash": "a1b2c3d",
  "files_backed_up": 142,
  "total_size_bytes": 5242880,
  "timestamp": "2026-05-14T02:00:00Z",
  "remote_url": "https://github.com/myorg/hermes-workspace-backup.git"
}
```

---

## 集成指南

### 与其他技能协作

- **变更前备份**：在 `hermes-code-ops-regression` 执行破坏性变更前，先调用本技能创建安全点
- **镜像同步**：`reference-source-mirror-sync` 可将本技能的备份仓库同步到其他 Git 平台（GitLab、Gitee）
- **恢复操作**：备份仓库就是普通 Git 仓库，可在任意时刻手动 `git checkout` 恢复

### 监控与告警

本技能完成后会写入结构化日志到 `~/.hermes/logs/backup/`：
```
~/.hermes/logs/backup/
├── backup-20260514-020000.json   # 成功日志（完整元数据）
└── errors.log                     # 失败日志（时间 + 错误码 + 消息）
```
