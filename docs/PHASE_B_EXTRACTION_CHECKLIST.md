# Phase B Extraction Checklist (Planning Only)

Last updated: 2026-06-04  
Scope: Documentation only. No code refactor in this phase.

## Objective

Prepare a safe, test-gated extraction from monolithic `bot.py` to FastAPI + service modules while preserving current Telegram behavior.

Source references:
- `docs/ARCHITECTURE.md`
- `docs/SERVICE_BOUNDARIES.md`
- `docs/API_CONTRACTS.md`
- `docs/TEST_STRATEGY.md`
- `docs/OBSERVABILITY.md`
- `docs/TECHNICAL_DEBT.md`

---

## 1) Extraction Order

1. `memory_service`
2. `finance_service`
3. `gmail_service`
4. `document_service`
5. `assistant_service`
6. Telegram adapter

Rationale: move lower-blast-radius domain services first, orchestrator last.

---

## 2) Service-by-Service Checklist

## 2.1 memory_service

- Current functions to extract:
  - `save_semantic_memory`, `search_semantic_memory`
  - `should_store_semantic_memory`, `looks_like_low_value_memory_text`, `filter_semantic_results`
  - `detect_memory_save_command`, `detect_memory_recall_topic`
  - `save_explicit_memory_content`, `format_memory_recall_response`
- Target module path:
  - `core/services/memory_service.py`
  - `core/repositories/memory_repo.py`
- Dependencies:
  - Supabase REST (`semantic_memory`, `personal_memory`, `events_log`)
  - embeddings client (OpenAI)
  - finance guard helper usage for restricted sources
- Risks:
  - memory quality regression (transient question pollution)
  - source-policy regression (document_note/insurance blocking)
- Tests required before extraction:
  - golden tests: Read/Remember/Save flows
  - memory save/recall regression tests
  - explicit source-policy tests
- Success criteria:
  - recall quality unchanged or better
  - explicit saves still deterministic
  - no finance-critical leakage into semantic memory from blocked sources

## 2.2 finance_service

- Current functions to extract:
  - `parse_finance_amount`, `classify_finance_message`, `is_critical_finance_capture_request`
  - `save_financial_profile_values`, `insert_financial_commitment`, `insert_financial_goal`, `insert_financial_plan`
  - `fetch_finance_rows`, `format_finance_profile_summary`
  - `set_finance_pending_confirmation`, `execute_finance_pending_action`
- Target module path:
  - `core/services/finance_service.py`
  - `core/repositories/finance_repo.py`
  - `core/policies/finance_guard.py`
- Dependencies:
  - Supabase finance tables
  - service-role headers
  - guided flow state contract
- Risks:
  - critical save failures due to auth/header drift
  - silent overwrite regressions
  - amount parsing regression for EU/US formats
- Tests required before extraction:
  - finance save/read test
  - amount parsing matrix tests
  - confirmation/edit/cancel flow tests
- Success criteria:
  - profile writes succeed only after explicit confirmation
  - no casual-text critical finance persistence
  - profile rendering parity with current output

## 2.3 gmail_service

- Current functions to extract:
  - `parse_gmail_search_intent`, `search_gmail_messages`, `get_gmail_summary`
  - `clean_gmail_snippet`, `format_gmail_search_results`, `extract_gmail_result_count`
  - `get_google_credentials`, `create_gmail_draft`
- Target module path:
  - `core/services/gmail_service.py`
  - `core/integrations/google_auth.py`
- Dependencies:
  - Google OAuth credentials/token refresh
  - Gmail API client
- Risks:
  - fallback to semantic/LLM for live Gmail questions
  - auth failure handling mismatch
  - raw JSON formatting regression
- Tests required before extraction:
  - Gmail search routing tests
  - no-result and auth-failure tests
  - draft-flow state tests (no send)
- Success criteria:
  - Gmail intent always calls Gmail API
  - concise formatted output parity
  - re-auth message preserved on auth failure

## 2.4 document_service

- Current functions to extract:
  - `save_document_metadata`, `get_uploaded_documents`, `get_documents_summary`
  - `summarize_read_request_content`
  - document-related ingestion helpers from `handle_document`
- Target module path:
  - `core/services/document_service.py`
  - `core/repositories/document_repo.py`
- Dependencies:
  - Supabase document tables
  - PDF parser path
  - semantic chunk storage path
- Risks:
  - accidental auto-save from `Read it`
  - metadata consistency drift (`storage_status`, chunk counts)
- Tests required before extraction:
  - read/summarize without auto-save tests
  - explicit save-as-document-note tests
  - document summary/list tests
- Success criteria:
  - Read-it behavior unchanged
  - document note flow remains explicit
  - metadata writes remain consistent

## 2.5 assistant_service

- Current functions to extract:
  - `build_live_context`, `format_with_claude`
  - identity routing logic (`is_identity_question`, identity response path)
  - orchestration helpers now spread in `handle_message`
- Target module path:
  - `core/services/assistant_service.py`
  - `core/router/intent_router.py`
- Dependencies:
  - all domain services
  - prompt policy/constants
- Risks:
  - routing priority regressions
  - unsupported-action safety wording regressions
  - token-usage regression due to duplicate context injection
- Tests required before extraction:
  - golden prompt matrix
  - route precedence tests
  - identity determinism tests
- Success criteria:
  - route parity with existing behavior
  - no hallucinated action confirmations
  - token-usage guardrails preserved

## 2.6 Telegram adapter

- Current functions to isolate:
  - `main`, handler registrations
  - `handle_message`, `handle_voice`, `handle_document`
  - `send_clean_reply`, `clean_telegram_text`, `split_telegram_chunks`
- Target module path:
  - `adapters/telegram/telegram_adapter.py`
- Dependencies:
  - FastAPI `/chat` and domain endpoints
  - keyboard/menu renderer
- Risks:
  - state mismatch between Telegram `context.user_data` and API sessions
  - menu/callback behavior drift
- Tests required before extraction:
  - end-to-end Telegram smoke tests
  - callback routing tests
- Success criteria:
  - Telegram UX unchanged
  - adapter is thin transport-only layer

---

## 3) FastAPI Bootstrap Plan (No Implementation Yet)

## Proposed app structure

```text
app/
  main.py
  api/
    routes_chat.py
    routes_memory.py
    routes_finance.py
    routes_gmail.py
    routes_documents.py
  core/
    services/
    repositories/
    policies/
  shared/
    config.py
    logging.py
    errors.py
    schemas.py
```

## Auth approach

- Phase B internal mode: backend token/header allowlist for Telegram adapter.
- Keep single-owner security posture.
- Preserve service-role usage server-side only; never expose service-role to client adapters.

## Request ID middleware

- Inject `request_id` for each HTTP request.
- Attach to logs and error responses.
- Propagate to downstream service calls.

## Health endpoint

- `GET /health`
- returns status for:
  - app runtime
  - Supabase connectivity
  - Gmail auth readiness (non-sensitive)
  - optional integration readiness flags

## Error response format

```json
{
  "error": {
    "code": "ROUTING_ERROR",
    "message": "Unable to route request",
    "request_id": "req_abc123"
  }
}
```

---

## 4) Telegram Adapter Plan

- Telegram should call Bajrang Core via FastAPI (`POST /chat`) for message orchestration.
- Keep existing keyboard/callback UX in adapter.
- Adapter responsibilities:
  - parse update
  - collect local session keys
  - call API
  - render cleaned/chunked reply
- Preserve behavior:
  - keep command/button labels unchanged
  - keep safe confirmations and guardrails unchanged
  - keep voice/document entry points unchanged initially

Fallback strategy:
- Feature-flag mode:
  - `USE_CORE_API=true` -> API path
  - `USE_CORE_API=false` -> current in-process path
- If API call fails or times out, fallback to in-process path during migration window.

---

## 5) Safety Gates (Mandatory Before/After Each Extraction Step)

1. `python -m py_compile bot.py`
2. Golden tests pass for affected area
3. Finance save/read test pass
4. Memory save/recall test pass
5. Gmail search routing/output test pass
6. Dashboard health test pass (`System Status` + `Show Errors`)

Release gate: no service extraction moves forward with red checks.

---

## 6) Stop Conditions (Pause Extraction Immediately)

1. Critical finance write regression (save failure or silent overwrite risk)
2. Gmail live query routed to fallback/LLM instead of Gmail API
3. Identity answer inconsistency
4. Memory source-policy break (document/insurance blocked incorrectly or finance leakage)
5. Telegram callback/menu break causing unusable UX
6. Observability blind spot (missing request trace for failures)
7. Any security regression exposing finance data or service-role misuse

When paused:
- rollback to previous stable step
- log incident in `docs/INCIDENTS.md`
- add/adjust regression test before resuming

---

## Recommended First Extraction Target

**Start with `memory_service`.**

Why:
- well-bounded function group,
- lower external side effects than finance writes,
- immediate value by reducing orchestration complexity,
- high regression detectability with existing memory test scenarios.
