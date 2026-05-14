# Contributing to Hermes Workspace

Thanks for your interest! Hermes is an open-source AI team workspace.

## Quick Start

```bash
git clone https://github.com/jack-wz/hermes-platform
cd hermes-platform
pip install -e ".[dev]"
hermes version
```

## Development Flow

1. **Find something to work on** — check [Issues](https://github.com/jack-wz/hermes-platform/issues)
2. **Create a branch** — `git checkout -b feat/my-feature`
3. **Write code + tests** — 17 existing tests as reference
4. **Run tests** — `python3 -m pytest tests/ -v`
5. **Submit PR** — with description of what changed and why

## Project Structure

```
build/
  phase1/    SKILL.md v1 specification
  phase2/    hermes-scan security analyzer
  phase3/    hermes-audit receipt system
  phase4/    Plugin Bridge + Extension Guide
  phase5/    Registry + Marketplace + Connector + Sandbox
  phase6/    MCP Gateway (multi-model routing)
  workspace/ Dashboard + Coworker Engine + Memory
registry/
  skills/    SKILL.md skill files
  coworkers/ AI coworker definitions
docs/        Competitive analysis, positioning, integration guides
tests/       17 unit + 10 integration tests
```

## Adding a Skill to Registry

1. Create a SKILL.md file with proper frontmatter (see `build/phase1/example-skill.SKILL.md`)
2. Run security scan: `hermes scan path/to/SKILL.md --json`
3. Test in sandbox: `hermes sandbox path/to/SKILL.md`
4. Publish: `hermes registry publish path/to/SKILL.md`

## Writing a Plugin

See the [Plugin Bridge TypeScript SDK](build/phase4/hermes_plugin_bridge/ts-sdk/) for typed interfaces.

```typescript
import { Plugin, PluginManifest } from '@hermes-workspace/plugin-sdk';

class MyPlugin extends Plugin {
  async initialize() { /* setup */ }
  async shutdown() { /* cleanup */ }
}
```

## Testing

```bash
# Unit tests
python3 -m pytest tests/test-memory.py -v

# Integration tests (requires running dashboard)
python3 build/workspace/hermes-dashboard.py &
python3 tests/test-integration.py
```

## Questions?

Open an [Issue](https://github.com/jack-wz/hermes-platform/issues) or start a Discussion.
