# Agent Alignment Rule

> **Governance Rule** — Immutable. Agent-override requires CEO approval.
> **Status**: Active
> **Date**: 2026-05-15
> **Source**: Distilled from mattpocock/skills `/grill-with-docs` methodology
> **Applies to**: All Hermes agents (board, team, and coworker level)

---

## Rule

**Before executing any non-trivial task, an agent MUST establish alignment with the requester.**

Alignment means:
1. The agent understands WHAT is being asked
2. The agent and requester share the same vocabulary (per `CONTEXT.md`)
3. Ambiguous requirements have been clarified through questioning
4. The scope and acceptance criteria are explicit

---

## When Alignment Is Required

| Task Type | Alignment Required? | Method |
|---|---|---|
| **Non-trivial implementation** (>3 tool calls expected) | ✅ Required | Full grilling session |
| **Cross-board task** (affects multiple boards) | ✅ Required | Full grilling + handoff plan |
| **Architecture change** (new component, schema change) | ✅ Required | ADR draft + grilling |
| **Unclear requirement** (user request is vague) | ✅ Required | Clarifying questions |
| **Status check / lookup** | ❌ Skip | Direct execution |
| **Follow-up in same session** (context already aligned) | ❌ Skip | Direct execution |
| **Scheduled cron job** (pre-defined scope) | ❌ Skip | Execute per definition |

---

## Grilling Protocol

When alignment is required, the agent follows this protocol:

### Phase 1: Load Shared Language
```
1. Load CONTEXT.md to establish shared vocabulary
2. Identify domain terms relevant to this task
3. Note any terminology gaps (new concepts not yet in CONTEXT.md)
```

### Phase 2: Clarify Ambiguity
```
1. Identify what is NOT clear about the request
2. Ask targeted questions (max 5 at a time)
3. Wait for answers before proceeding
4. Repeat until all ambiguity is resolved
```

### Phase 3: Confirm Scope
```
1. Restate the task in your own words using CONTEXT.md terms
2. List what IS in scope
3. List what IS NOT in scope (equally important)
4. State acceptance criteria: "Done means..."
5. Ask for explicit confirmation before starting
```

### Phase 4: Record
```
1. Save alignment artifact (clarified spec) for audit
2. Update CONTEXT.md if new terms were introduced
3. Proceed to execution
```

---

## Non-Compliance

An agent that skips alignment and produces misaligned output:
1. The output is rejected (wasted tokens, wasted time)
2. The agent must re-execute WITH alignment
3. Repeated violations escalate to CEO review

---

## Relationship to Other Rules

- **Handoff Protocol**: Alignment is required BEFORE handoff (the handing-off agent must align with the receiving agent)
- **Correction Precedence**: L3 Persona corrections override any alignment — agents must follow corrections even if they contradict the aligned scope
- **Cron Jobs**: Pre-aligned by definition (scope is set at cron creation time)

---

## Quick Reference

```
IF task is non-trivial AND not pre-aligned:
    1. Load CONTEXT.md
    2. Grill (clarify ambiguity)
    3. Confirm scope + acceptance criteria
    4. Record alignment artifact
    5. Execute

IF task is trivial OR pre-aligned:
    Execute directly
```
