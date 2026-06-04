# Observability Plan (Phase A.5)

Last updated: 2026-06-04  
Reference incidents: `docs/INCIDENTS.md`

## Objectives

- Make routing and save failures diagnosable in one pass.
- Track action intent -> API call -> result path clearly.
- Reduce time-to-root-cause for regressions.

## Logging Standard (Target)

Use structured logs (JSON shape), even if stdout is still plain text today.

Required fields:
- `timestamp`
- `level`
- `request_id`
- `correlation_id` (chat/session/thread scope)
- `module`
- `action`
- `status` (`success`, `failed`, `blocked`)
- `duration_ms` (where possible)
- `error_code` (optional)
- `message` (short human-readable)

Sensitive-data rule:
- Never log tokens/credentials.
- Never log full email body/snippet payloads.
- Avoid logging salary/rent exact values unless explicitly needed for diagnostics.

## Request ID and Correlation ID

- Generate `request_id` at the start of each inbound message.
- Persist across all internal calls and external API calls.
- Add `correlation_id` tied to Telegram chat/user session for multi-step flows.
- Include both IDs in `log_system_error` writes to `system_logs` (future schema extension).

## Error Categories

1. `AUTH` - OAuth token/permission/service-role failures
2. `ROUTING` - wrong handler/intent chosen
3. `VALIDATION` - parse/format/state mismatch
4. `EXTERNAL_API` - Gmail/Calendar/Asana/Render/GitHub call failures
5. `DB` - Supabase write/read/migration mismatch
6. `POLICY_BLOCK` - deliberate safety block (finance/memory guards)

## Health and Alerting Baseline

Track:
- command success rate (`system status`, Gmail queries, finance saves)
- top failing modules from `system_logs`
- auth failure counts (`401`, `403`, refresh errors)
- slow operations (`duration_ms > threshold`)

## Incident Workflow

1. Detect: user report or health-check anomaly.
2. Triage: map to category and severity (Critical/High/Medium/Low).
3. Stabilize: apply narrow safe fix.
4. Verify: compile + targeted manual scenarios.
5. Record: add/update incident in `docs/INCIDENTS.md`.
6. Prevent: add golden test case.

## Immediate Improvements (No Refactor Needed Yet)

- Add request/correlation IDs in logs before FastAPI extraction.
- Standardize one-line intent logs for all external actions.
- Add `operation` and `table` fields consistently for finance DB failures.
