# Technical Debt and Extraction Risks

Last updated: 2026-06-04  
Scope: Architecture risk review for FastAPI extraction readiness.

## High Risk

1. Telegram coupling in `handle_message`
- Symptom: orchestration, business rules, and transport details are mixed.
- Risk: high regression chance during extraction.
- Recommendation: introduce service wrappers, keep handler as thin adapter.

2. Global mutable state + environment reliance
- Symptom: global clients/keys/constants used across many functions.
- Risk: testability and runtime configuration drift.
- Recommendation: central config object and dependency injection during Phase B.

3. `context.user_data` state-machine sprawl
- Symptom: many flow flags (`waiting_for_*`, pending confirmation keys).
- Risk: cross-flow collisions and hard-to-debug routing edges.
- Recommendation: formal state schemas per flow with namespaced keys.

4. Direct Supabase REST calls spread across domains
- Symptom: repeated `requests.*` logic with per-function payload handling.
- Risk: inconsistent error handling and auth behavior.
- Recommendation: table-specific repository layer per domain service.

5. External integrations called inline from chat path
- Symptom: Gmail/Calendar/Asana calls inside message orchestration.
- Risk: latency spikes and mixed concerns.
- Recommendation: service-level action functions with uniform result envelopes.

## Medium Risk

1. Callback and command routing complexity
- Many keyword paths and precedence checks in one function.
- Add route tests and eventual router abstraction.

2. Observability field consistency
- Logging exists, but request correlation is incomplete.
- Add request_id/correlation_id standard.

3. Mixed formatting responsibilities
- Telegram cleaning/chunking mixed with domain outputs.
- Isolate transport formatting adapters.

4. Legacy or duplicate helper drift
- Large single-file structure increases duplicate risk over time.
- Add lint rules and periodic function ownership review.

## Low Risk

1. Docs fragmentation risk
- Mitigated by `docs/WORKFLOW.md` and `docs/NEXT_STEPS.md`.

2. Migration process clarity
- Supabase migrations are present and consistent; continue incremental migrations.

## Top 5 Architectural Risks (Priority Order)

1. Monolithic `handle_message` routing
2. Stateful flow collisions via `context.user_data`
3. Inline external API calls in orchestration path
4. Distributed direct DB access patterns
5. Missing end-to-end correlation IDs

## Readiness Score for FastAPI Extraction

Score: **72 / 100**

Rationale:
- Strong: stabilized features, incident history, migration discipline, guardrails.
- Gaps: boundary separation and adapter/service decoupling still pending.

## Go/No-Go Recommendation

Go for Phase B preparation after:
1. Golden prompt baseline is defined (this is now documented).
2. Service wrappers are introduced without behavior changes.
3. Request/correlation logging is standardized.
