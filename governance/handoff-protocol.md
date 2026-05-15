# Agent Handoff Protocol

> **Governance Rule** — Immutable. Agent-override requires CEO approval.
> **Status**: Active
> **Date**: 2026-05-15
> **Source**: Distilled from mattpocock/skills `/handoff` methodology
> **Applies to**: All cross-agent task transfers

---

## Rule

**When a task is transferred from one agent to another, a structured handoff document MUST be created.**

The handoff ensures the receiving agent has everything needed to continue without re-discovering context. No agent should ever say "what was the previous agent doing?"

---

## Handoff Document Template

Every handoff MUST contain these 7 sections:

```markdown
# Handoff: [Task Name]

## 1. Task Summary (1-2 sentences)
What is being built/fixed/investigated. Use CONTEXT.md terms.

## 2. Current State
- [ ] What's done
- [ ] What's in progress (exactly where the agent stopped)
- [ ] What's NOT started yet

## 3. Key Decisions Made
- Decision → Reason → Impact
- (Link to ADR if applicable)

## 4. Open Questions
- Question → Who needs to answer it
- Blocked? (yes/no)

## 5. Files & Artifacts
- Absolute paths to all modified/created files
- Capsule IDs, commit hashes, issue numbers
- Test results (passing? failing?)

## 6. Next Steps (actionable)
1. [Next immediate action — what the receiving agent should do first]
2. [Second action]
3. ...

## 7. Context References
- Memory tiers used (L1/L2/L3 entries)
- Relevant ADRs
- Relevant governance rules
```

---

## When Handoff Is Required

| Scenario | Handoff Required? |
|---|---|
| Task moves from one board to another | ✅ Full handoff |
| Task moves between teams in same board | ✅ Full handoff |
| Same agent continues (session resumes) | ❌ No handoff needed |
| Cron job output consumed by another cron | ✅ Light handoff (summary only) |
| CEO reassigns task mid-execution | ✅ Full handoff |

---

## Handoff Storage

Handoff documents are stored at:
```
os/active/handoffs/YYYY-MM-DD/<task_id>-handoff.md
```

The sending agent writes the handoff. The receiving agent reads it before starting.

---

## Anti-Patterns (Prohibited)

| ❌ Anti-Pattern | ✅ Correct |
|---|---|
| "Continue the work" with no context | Full handoff document |
| "See git log for details" | Explicit file paths + commit hashes |
| "The previous agent knows" | Self-contained document — no oral tradition |
| Skipping handoff because "it's obvious" | Write it anyway — what's obvious to you isn't obvious to the next agent |

---

## Quick Reference

```
IF task is being transferred:
    1. Write handoff document using the 7-section template
    2. Save to os/active/handoffs/YYYY-MM-DD/<task_id>-handoff.md
    3. Notify receiving agent with handoff path
    4. Receiving agent: read handoff BEFORE any tool calls
```
