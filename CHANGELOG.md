# Changelog

All notable changes to Hermes Workspace will be documented in this file.

## [2.0.0] — 2026-05-14

### Added
- **MCP Gateway** (`build/phase6/hermes-gateway.py`) — multi-model routing engine
  - 6 models across 4 providers (Anthropic, OpenAI, Google, DeepSeek)
  - 10 task-type routing rules with capability scoring
  - REST API server (port 5005)
- **Unified CLI** (`hermes`) — single entry point for all tools
  - `hermes serve` / `registry` / `scan` / `audit` / `sandbox` / `memory` / `coworker` / `connect`
- **pip-installable package** (`pyproject.toml`) — `pip install hermes-workspace`
- **Skill Sandbox** (`build/phase5/hermes-sandbox.py`) — isolated pre-publish testing
  - PASS/WARN/FAIL/TIMEOUT status with permissions tracking
- **Multi-Channel Connector** (`build/phase5/hermes-connector.py`) — Feishu/Slack/Discord
  - Unified BaseConnector abstraction with webhook server (port 5004)
- **SKILL.md Converter** (`build/phase5/hermes-convert.py`) — GitHub → SKILL.md
  - Auto-infers tags, security metadata, permissions from repo API
- **Plugin Bridge TypeScript SDK** (`ts-sdk/`) — typed plugin interfaces
  - Plugin/PluginManifest/HookHandler base classes
  - PluginRegistry singleton with hook execution chain
- **Registry v2** — Marketplace API (`/skills`, `/search`, `/stats`, `/health`)
  - `install`, `publish`, `export` commands
- **7 Registry Skills** (3 scored + 4 converted)
  - Cronalytics A/91, Hawkins A/85, GateMem B/72
  - Claude Design 300★, Design Toolkit 100★, Power Design 227★, Visual Taste Lab 27★

### Changed
- **Memory v1.2** — namespace isolation (shared/personal/board/audit)
  - GateMem-compatible export (`gate_mem_compat_export()`)
  - Audit hashing on namespace entries
- **Dashboard** — real subprocess execution for `/api/coworkers/run`
  - New endpoints: `/api/memory/namespaces`, `/api/memory/gate-mem`
- **README** — competitive comparison table (7 dimensions × 5 competitors)
  - Architecture diagram, 8 coworkers table

### Fixed
- Dashboard `/api/coworkers/run` was a no-op stub → now spawns actual subprocess
- Docker: multi-stage build, non-root user, HEALTHCHECK
- hermes-convert.py null license handling

### Ecosystem
- Hawkins contact (hermes-platform#1)
- SkillDock contact (hermes-platform#2 + wanghuan9/skill-manager#1)
- skills-manager contact (xingkongliang/skills-manager#148)

## [1.1.0] — 2026-05-14

### Added
- Real coworker execution via subprocess (was log stub)
- Memory context endpoint (`/api/memory/context`)
- 10 integration tests (cross-component)
- CI/CD: GitHub Actions workflow (unit + integration + docker + lint)
- Docker multi-stage build with health check
- `.dockerignore`, pinned requirements

## [1.0.0] — 2026-05-14

### Added
- Platform kernel: SKILL.md v1, hermes-scan, hermes-audit, Plugin Bridge
- Workspace: Dashboard (Flask), Coworker Engine, 8 AI coworkers
- Shared Memory: "correct once, all remember"
- Registry: skills.json + hermes-registry.py CLI
- Docker: single-container deployment
- 10 unit tests (SharedMemory API)
- MIT License
