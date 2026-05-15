# ADR-003: Progressive Disclosure Injection Strategy

**Status**: Accepted
**Date**: 2026-05-15
**Deciders**: CEO + team_skillops
**Applies to**: All agent session initialization

---

## Context

Hermes v1.x injected the entire `SHARED_MEMORY.md` into every agent session prompt. As memory grew, this caused:

1. **Token bloat**: Every agent loaded all entries regardless of relevance
2. **Attention dilution**: Important corrections buried in noise
3. **Cost scaling**: Token cost grew linearly with memory size

The TencentDB-Agent-Memory architecture demonstrated "progressive disclosure" — inject only the highest-signal tier by default, with drill-down into lower tiers on demand.

## Decision

**Adopt progressive disclosure: default inject L3 Persona only, drill down on demand.**

Injection hierarchy:
1. **L3 Persona** — Always injected (CEO preferences, corrections, constraints). ~200-500 tokens.
2. **L2 Scenario** — Injected when task context matches a known scenario pattern. ~100-300 tokens.
3. **L1 Atom** — Summary only (count + types). Drill-down via `search_memory()` or `get_tier_entries('l1')`.
4. **L0 Conversation** — Never injected. Accessed only via `drill_down(node_id)` when tracing evidence.

Fallback: If L3/L2 tiers are empty, fall back to legacy flat memory injection.

## Consequences

- ✅ Token savings: 70-90% reduction in memory injection (from full file to L3-only)
- ✅ Higher signal-to-noise: agents see only the most relevant context
- ✅ Cost scaling: memory cost stays flat regardless of total memory size
- ✅ Evidence preservation: L0 is never deleted, always drill-down-able
- ⚠️ Requires discipline: L3 must be kept updated via distillation pipeline
- ⚠️ Cold start: new agents with empty tiers fall back to full injection

## Implementation

Method: `SharedMemory.get_tiered_context()` (Phase A, `hermes-memory.py`).

```python
# Default agent injection:
context = memory.get_tiered_context()
# → L3 Persona (always)
# → L2 Scenario (if relevant)
# → L1 Atom count (summary)
# → L0 count (reference only)
```

## Alternatives Considered

| Alternative | Reason Rejected |
|---|---|
| Inject all tiers | Defeats purpose — token bloat returns |
| Inject L3 only, no drill-down | Loses evidence traceability |
| RAG/vector search | External dependency, no tier semantics |

## References

- ADR-001: 4-Tier Memory Architecture
- `build/workspace/hermes-memory.py::SharedMemory.get_tiered_context()`
- TencentDB-Agent-Memory progressive disclosure pattern
