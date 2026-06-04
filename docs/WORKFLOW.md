# Bajrang Lean Workflow (Low Cost, High Consistency)

Last updated: 2026-06-04

## Goal
Keep one source of truth in the repo, reduce token usage, and avoid copy-paste across tools.

## Single Source of Truth
Use these files only:

- `docs/BAJRANG_VISION.md` - long-term direction
- `docs/BAJRANG_ROADMAP.md` - phase-level plan
- `docs/DECISIONS.md` - architecture/product decisions
- `docs/INCIDENTS.md` - what broke and what we fixed
- `docs/NEXT_STEPS.md` - current execution queue

## Weekly Loop
1. Review `docs/NEXT_STEPS.md`
2. Pick top 1-3 items for the week
3. Implement in small batches
4. Run compile/tests
5. Update `DECISIONS.md` and `INCIDENTS.md` only if needed
6. Mark done items and add next items

## Session Start Prompt (Use This)
Copy this at the start of a session:

```text
Use docs/BAJRANG_ROADMAP.md, docs/DECISIONS.md, docs/INCIDENTS.md, and docs/NEXT_STEPS.md as source of truth.
Work only on NEXT_STEPS.md top priorities.
Keep changes scoped and token-efficient.
After changes, update NEXT_STEPS.md status and summarize files changed.
```

## Token Cost Guardrails
- Ask for "diff-only summary" unless deep explanation is needed.
- Request "edit only these files" to keep scope tight.
- Prefer one feature/fix per turn.
- Avoid repeating full history in prompts; reference docs instead.
- Use smaller/medium models for routine edits and docs; reserve high model for complex architecture/debug tasks.

## Model Level Guidance
- Low: formatting, docs cleanup, small UI text fixes, straightforward refactors
- Medium: normal feature changes, handler routing, migrations, integration fixes
- High: architecture pivots, cross-system regressions, risky production debugging

## Definition of Done (Per Change)
- Code updated and scoped
- `python -m py_compile bot.py` passes
- Relevant doc updated (if behavior changed)
- Short rollback note included when risk is non-trivial
