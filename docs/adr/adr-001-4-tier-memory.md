# ADR-001: 4-Tier Memory Architecture

**Status**: Accepted
**Date**: 2026-05-15
**Deciders**: CEO + team_skillops
**Supersedes**: Flat-file SHARED_MEMORY.md (v1.0-v1.2)

---

## Context

Hermes v1.x used a single flat Markdown file (`SHARED_MEMORY.md`) for team memory. As the organization grew to 3 boards × 6+ teams, this approach showed critical limitations:

1. **No stratification**: All memory types (corrections, facts, logs) mixed in one file
2. **Token waste**: Full memory injected into every agent session
3. **No distillation**: Raw entries never aggregated into higher-level patterns
4. **No progressive disclosure**: Agents couldn't choose what level of detail to load

External reference: TencentDB-Agent-Memory (1,494★) demonstrated a 4-tier pipeline (L0→L1→L2→L3) with 61% token reduction and 51% pass rate improvement on WideSearch benchmarks.

## Decision

**Adopt a 4-tier memory architecture**, distilled from TencentDB-Agent-Memory:

```
L0 — Conversation (raw logs, never modified)
L1 — Atom (extracted facts, JSONL, confidence-weighted)
L2 — Scenario (clustered patterns, Markdown)
L3 — Persona (synthesized profile, Markdown)
```

Key principles:
1. Evidence never lost (L0 is append-only)
2. Top tier human-readable (L3 is plain Markdown)
3. Progressive disclosure (default inject L3 only)
4. Zero external npm dependencies (pure Python)

## Consequences

- ✅ Token savings: 40-83% on tool-heavy sessions (Phase C SymbolicMemory)
- ✅ Structured retrieval: drill-down from L3→L2→L1→L0 by node_id
- ✅ Backward compatible: all v1.x API methods preserved
- ⚠️ Migration cost: existing flat memory must be migrated (automated via `migrate_from_flat()`)
- ⚠️ Maintenance: 4 directories to manage vs 1 file

## Alternatives Considered

| Alternative | Reason Rejected |
|---|---|
| Vector DB (Chroma/Pinecone) | External dependency, opaque retrieval, no tier structure |
| Flat file + grep | No stratification, no distillation, no compression |
| npm @tencentdb-agent-memory | License "Other" (non-MIT), external npm dependency |
| SKILL.md memory blocks | Format mismatch — SKILL.md is for skills, not operational memory |

## References

- `docs/architecture/memory-v2-tencentdb-distillation.md`
- TencentDB-Agent-Memory: https://github.com/Tencent/TencentDB-Agent-Memory
- Implementation: `build/workspace/hermes-memory.py` (Phase A+B+C, ~1300 lines)
