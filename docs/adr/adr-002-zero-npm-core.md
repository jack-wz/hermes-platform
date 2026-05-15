# ADR-002: Zero External npm Dependencies for Core

**Status**: Accepted
**Date**: 2026-05-15
**Deciders**: CEO + team_skillops
**Applies to**: Memory v2 Phase A-C, SymbolicMemory, DistillationPipeline

---

## Context

When evaluating the TencentDB-Agent-Memory architecture for Hermes adoption, we faced a choice:

- **Option A**: Install `@tencentdb-agent-memory/memory-tencentdb` via npm
- **Option B**: Distill the architecture into pure Python, evaluate npm later

The TencentDB package is TypeScript/npm with License "Other" (not standard MIT/Apache). Our platform core is Python/Flask, making npm an additional runtime dependency.

## Decision

**Zero external npm dependencies for all core memory components (Phase A-C).**

Strategy: B→A — distill architecture first, evaluate npm integration at Phase D.

Core components implemented in pure Python:
- `SharedMemory` (4-tier storage, ~1300 lines)
- `DistillationPipeline` (L0→L1→L2→L3, ~450 lines)
- `SymbolicMemory` (Mermaid graph compression, ~420 lines)

## Consequences

- ✅ Zero runtime dependency risk (no npm supply chain exposure)
- ✅ Full control over implementation (can modify any behavior)
- ✅ Single language stack (Python end-to-end)
- ✅ License safety (MIT for our code vs "Other" for TencentDB)
- ⚠️ Slower initial delivery (build from scratch vs install-and-configure)
- ⚠️ Must maintain our own distillation heuristics (Phase B uses regex, not LLM)

## Phase D (Future)

When Phase D is reached:
- Evaluate `@tencentdb-agent-memory` as an optional plugin
- Compare our heuristics vs TencentDB's LLM-based extraction
- Decision: adopt, wrap, or continue self-maintained

## Alternatives Considered

| Alternative | Reason Rejected |
|---|---|
| npm install immediately | License risk, adds npm to Python stack |
| Skip distillation, stay flat | Already proven inadequate (ADR-001) |
| Use vector DB instead | External dep, no tier structure |

## References

- ADR-001: 4-Tier Memory Architecture
- `docs/architecture/memory-v2-tencentdb-distillation.md`
