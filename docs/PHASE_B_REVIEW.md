# Phase B Review (B.1-B.5)

Last updated: 2026-06-04 (B.7 update)  
Scope: Review + cleanup (no feature behavior changes).

## 1) Extraction Summary

Completed extractions:
- `services/memory_service.py`
- `services/finance_service.py`
- `services/gmail_service.py`
- `services/document_service.py`
- `services/assistant_service.py`

Current integration pattern:
- `bot.py` still owns Telegram handlers and menu/callback flow.
- Service extraction is implemented through compatibility wrappers in `bot.py`.
- Behavior has remained stable by preserving function signatures and routing order.

## 2) Wrapper Duplication Audit (`bot.py`)

Audit result after B.7 cleanup:
- Duplicate function definitions in `bot.py`: **0**
- Compatibility wrappers were reduced to only helper wrappers still used directly by Telegram handlers (`build_runtime_context`, `build_conversation_history`, `query_assistant_response`, PDF helper wrappers).

Registry safety note:
- Command/context registries remain stable after cleanup because duplicate late re-definitions were removed rather than reordered.

### Classification

Safe to remove now:
- Removed in B.7:
  - duplicate finance wrappers
  - duplicate Gmail wrappers
  - duplicate document wrappers that shadowed existing definitions
  - duplicate assistant wrappers that shadowed existing definitions

Remove later (planned cleanup pass):
- legacy in-module domain implementations that are not yet fully delegated to service modules.

Keep temporarily:
- thin Telegram-facing helper wrappers used by handler orchestration and document flow.

Keep permanently:
- none required; target is explicit service interfaces behind a thin adapter.

## 3) Wrapper Cleanup Strategy (Updated)

1. Continue service delegation in-place for remaining legacy domain bodies.
2. Keep registries stable while replacing implementation bodies with service calls.
3. Preserve handler route order and menu/callback behavior.
4. Re-run compile + regression checks after each delegation batch.
5. Keep only adapter-level orchestration in `bot.py`.

## 4) Telegram Adapter Readiness

Telegram-specific code still concentrated in `bot.py`:
- Message/callback/voice/document handlers
- Menu rendering (`ReplyKeyboardMarkup`, button labels, callback flow)
- Telegram output formatting/chunking (`send_clean_reply`, clean/split helpers)
- Access checks (`ALLOWED_USER_ID`)

Business logic still inside handlers:
- `handle_message` still orchestrates end-to-end route priority.
- Multi-step flows still use inline branching and state transitions.

`context.user_data` dependency hotspots:
- memory flow states
- finance setup + pending confirmation
- email draft flow
- german learning flows
- voice reply toggles

Adapter extraction effort estimate:
- Medium-high
- Approx. 5-8 focused engineering days for clean adapter split with parity tests.

## 5) FastAPI Readiness Review

Current readiness score: **90 / 100**

Why not higher:
- Telegram and orchestration are still tightly coupled in `bot.py`.
- No formal runtime API boundary is active yet (contracts are documented only).
- Observability correlation IDs and request IDs are not end-to-end.

### Blockers before full FastAPI extraction

1. Complete remaining legacy-body delegation to services.
2. Handler orchestration split from transport-specific code.
3. End-to-end regression pack for route priority and safety guards.
4. Request-level observability correlation.

## 6) Regression Review (Post B.1-B.5)

Memory:
- Logic extracted.
- Source-aware save guards and low-value filtering preserved.
- Risk: duplicate definition drift if wrappers and originals diverge.

Finance:
- Logic extracted, including parsing and confirmation helpers.
- Service-role behavior preserved via delegated wrappers.
- Risk: dual definitions in one file increase maintenance overhead.

Gmail:
- Query parsing/search/formatting extracted.
- Auth and recovery behavior preserved.
- Risk: wrapper/original divergence over time.

Documents:
- Metadata/list/summary and PDF helper functions extracted.
- Read-it/document-note/PDF chunk behavior preserved.
- Risk: minor drift risk from shared helper usage paths.

Assistant orchestration:
- Core context and response helpers extracted.
- Routing remains in Telegram handler as intended.
- Risk: orchestration still centralized in a large handler.

Identity:
- Deterministic identity behavior remains intact.
- No regressions observed in routing layer structure.

## 7) Top 10 Risks

1. Duplicate function drift between old and wrapper definitions.
2. Function-reference capture in command/context registries.
3. Monolithic `handle_message` complexity.
4. Large `context.user_data` state surface and collision risk.
5. Mixed transport/domain responsibilities in one module.
6. Service boundary ambiguity during incremental cleanup.
7. Incomplete request/correlation observability.
8. Regression risk when removing old definitions.
9. Limited automated parity tests for route precedence.
10. Implicit global config dependencies across services.

## 8) Recommended Next Phase

**Phase B.8 - FastAPI Skeleton Prep (no behavior cutover)**

Goals:
- Stand up FastAPI skeleton with no production cutover.
- Keep Telegram adapter as primary runtime while adding dual-path scaffolding.
- Add compact parity smoke suite for core routes.

## 9) Phase C Entry Criteria (Recommended)

Move to Phase C only when all are true:
1. No duplicate domain function definitions remain in `bot.py`. (Done)
2. Telegram adapter responsibilities are isolated and documented.
3. Regression suite covers memory/finance/gmail/document/identity critical prompts.
4. Request-level logging correlation is in place.
5. API boundary contract is executable (even if minimal) and stable.

## 10) Go / No-Go for FastAPI Extraction

Verdict: **Go (Skeleton Only), Conditional for Cutover**

Interpretation:
- Go for FastAPI skeleton extraction and adapter boundary setup.
- Keep production Telegram path primary until parity/regression suite passes.
