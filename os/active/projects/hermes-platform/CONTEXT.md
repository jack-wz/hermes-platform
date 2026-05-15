# Hermes Platform — Shared Language (CONTEXT.md)

> **Purpose**: A glossary of domain terms shared by all Hermes agents.
> When an agent uses these terms, other agents understand exactly what is meant.
> This reduces verbosity, improves alignment, and cuts token waste.
>
> **Inspired by**: mattpocock/skills (83.8k★) — "A shared language has many benefits
> beyond reducing verbosity: variables are named consistently, the codebase is
> easier to navigate, and the agent spends fewer tokens on thinking."
>
> **Maintained by**: team_skillops
> **Last updated**: 2026-05-15

---

## Core Platform

| Term | Definition | Context |
|---|---|---|
| **Hermes Platform** | The multi-agent orchestration system. Comprises Dashboard, Marketplace, Registry, Memory, and Coworker subsystems. | All agents |
| **Coworker** | A sub-agent process managed by the Hermes orchestration layer. Each coworker has a role profile, skill set, and execution log. | Dashboard / Execution |
| **Registry** | The verified skill catalog (`registry/skills.json`). Skills are rated A-F based on security, quality, and Hermes compatibility. | Marketplace / SkillOps |
| **Marketplace** | The web UI for browsing, searching, and installing Registry skills. Served on port 5003. | Platform |
| **Dashboard** | The central web UI (`hermes-dashboard.py`, port 5002). Shows org status, Kanban board, coworker status, and memory tiers. | Platform |

---

## Organization

| Term | Definition | Context |
|---|---|---|
| **Board** | A top-level organizational unit. Three boards: Discovery (📡), Execution (⚡), Prediction (🔮). | Governance |
| **Team** | A functional group within a board. E.g., `team_build` under Execution, `team_signal` under Discovery. | Coworker |
| **Governance Rule** | An immutable constraint that agents must follow. Stored in `governance/`. Cannot be overridden by agents without CEO approval. | All agents |
| **WorldAction** | An organizational-level action record. JSON format, stored at `os/world/snapshot/world_actions.json`. | Discovery / Execution |
| **Snapshot** | A point-in-time capture of organizational state. Used for audit and cross-agent alignment. | All boards |

---

## Memory System (v2)

| Term | Definition | Context |
|---|---|---|
| **Memory v2** | The 4-tier memory architecture distilled from TencentDB-Agent-Memory. Replaces flat-file SHARED_MEMORY.md. | All agents |
| **Tier (L0-L3)** | One layer in the 4-tier pipeline. Each tier has a specific format and purpose. | Memory |
| **L0 — Conversation** | Raw conversation logs (Markdown). The evidence source — never deleted or modified. | Memory |
| **L1 — Atom** | Atomic facts extracted from L0 (JSONL). One fact per line, with confidence score and type tag. | Memory |
| **L2 — Scenario** | Clustered context patterns (Markdown). Groups of related L1 atoms with a thematic header. | Memory |
| **L3 — Persona** | Synthesized user/CEO profile (Markdown). Aggregated from L2 scenarios. Default injection tier. | All agents |
| **Distillation** | The process of extracting structured knowledge from raw data, moving up the tiers (L0→L1→L2→L3). | Memory / SkillOps |
| **Progressive Disclosure** | The injection strategy: default inject L3 only, drill down to L2/L1/L0 on demand. Saves tokens. | All agents |
| **Symbolic Memory** | Phase C compression: converting verbose tool logs into Mermaid symbol graphs with node_id→raw_log traceability. | Memory |

---

## Governance & Operations

| Term | Definition | Context |
|---|---|---|
| **Correction** | A human (CEO or team lead) instruction that overrides agent behavior. Corrections are stored in L3 Persona and injected into all agents. Highest priority signal. | All agents |
| **Capsule** | A knowledge intake record. JSON format, timestamped, stored at `os/active/capsules/YYYY-MM-DD/`. Tracks ecosystem evaluations, architecture decisions, and signal intakes. | Discovery / SkillOps |
| **Handoff** | The formal transfer of a task from one agent to another. Includes context summary, current state, and remaining work. (Protocol: `governance/handoff-protocol.md`) | All agents |
| **Alignment** | The pre-execution phase where an agent clarifies requirements with the user before starting work. Required by governance rule for all non-trivial tasks. | All agents |
| **Cron Job** | A scheduled autonomous task. Managed via `cronjob` tool. Runs in isolated sessions with no user interaction. | Ops |

---

## Development

| Term | Definition | Context |
|---|---|---|
| **Kanban** | The task tracking board (SQLite, `kanban.db`). Columns: todo/ready/in_progress/blocked/done. | Execution / Dashboard |
| **SKILL.md** | The standard skill definition format. YAML frontmatter + Markdown body. Used by Registry and Marketplace. | SkillOps |
| **Phase** | A development milestone in the platform build pipeline. Phases 1-7 defined in the project roadmap. | Build Team |
| **Spike** | A throwaway experiment to validate an idea before committing to full implementation. | Build Team |
| **Red-Green-Refactor** | The TDD cycle: write failing test → make it pass → refactor. Embedded in build governance. | Build Team |

---

## Ecosystem & Signal

| Term | Definition | Context |
|---|---|---|
| **Signal** | An external event, project, or trend relevant to Hermes strategy. Discovered by `team_signal`, evaluated by `board_discovery`. | Discovery |
| **Lead** | A qualified signal with potential for Hermes integration or competitive response. Verified by `team_growth`. | Discovery / Execution |
| **Intake** | The process of evaluating an external project for Hermes ecosystem value. Produces a Capsule and optionally a Registry entry. | SkillOps |
| **Distillation (Ecosystem)** | Extracting architecture, methodology, or code patterns from an external project into Hermes-native implementation. Strategy: B→A (distill first, evaluate npm later). | SkillOps |

---

## Key Architecture Decisions (ADR Index)

| ADR | Topic | Decision |
|---|---|---|
| ADR-001 | Memory Architecture | 4-tier pipeline (TencentDB distillation) over flat file |
| ADR-002 | External Dependencies | Zero npm deps for core (Phase A-C pure Python) |
| ADR-003 | Injection Strategy | Progressive disclosure: L3 default, drill-down on demand |

*Full ADR documents: `docs/adr/`*

---

## Usage Notes

1. **All agents** load this file at session start (via L2 Scenario injection).
2. When introducing a new term, add it here immediately — don't wait.
3. If two agents use different words for the same concept, pick one and standardize.
4. ADRs are append-only. To change a decision, write a new ADR that supersedes the old one.
