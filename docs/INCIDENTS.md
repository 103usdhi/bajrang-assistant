# Bajrang Incident Register

## INC-001 - Gmail intent not routed to Gmail API
- **Severity:** High
- **Area:** Gmail
- **Detected by:** User report
- **Symptom:** “most recent email from X” produced vague fallback responses.
- **Root Cause:** Intent parser/routing did not force Gmail API path.
- **Fix:** Added robust Gmail intent parsing + direct `search_gmail_messages()` routing.
- **Prevention:** Keep intent test set for “from”, “latest”, “did I get”, “search for”.
- **Status:** Closed

## INC-002 - Missing Gmail query observability
- **Severity:** Medium
- **Area:** Gmail
- **Detected by:** Debugging need
- **Symptom:** Couldn’t confirm real executed query.
- **Root Cause:** No intent debug log.
- **Fix:** Added non-sensitive log: intent type, query, max_results.
- **Prevention:** Standardize action-intent logs.
- **Status:** Closed

## INC-003 - Gmail output raw JSON in Telegram
- **Severity:** Medium
- **Area:** Gmail UX
- **Detected by:** User report
- **Symptom:** Raw JSON responses.
- **Root Cause:** Direct JSON serialization returned to chat.
- **Fix:** Added formatted result rendering, snippet cleanup, single-result mode, top-5 display.
- **Prevention:** Snapshot tests for Telegram-visible output.
- **Status:** Closed

## INC-004 - Advanced Gmail phrasing not recognized
- **Severity:** Medium
- **Area:** Gmail NLP
- **Detected by:** User report
- **Symptom:** “top 10 emails with subject...” not detected.
- **Root Cause:** Narrow intent patterns.
- **Fix:** Added advanced patterns (subject/from/containing/mentioning + count extraction).
- **Prevention:** Expand intent regression suite.
- **Status:** Closed

## INC-005 - Identity hallucination (wrong creator names)
- **Severity:** High
- **Area:** Assistant identity
- **Detected by:** User report
- **Symptom:** Inconsistent fake developer names.
- **Root Cause:** No deterministic identity source/handler.
- **Fix:** Added `docs/IDENTITY.md`, prompt hardening, explicit identity handler.
- **Prevention:** Guardrail tests for identity questions.
- **Status:** Closed

## INC-006 - Finance table grants too permissive
- **Severity:** Critical
- **Area:** Finance security
- **Detected by:** Review
- **Symptom:** Sensitive tables initially had broad role access.
- **Root Cause:** Grant migration allowed `anon/authenticated`.
- **Fix:** Added revoke migrations; restricted to service_role access model.
- **Prevention:** Security review checklist before applying grants.
- **Status:** Closed

## INC-007 - Finance profile save failed after hardening
- **Severity:** High
- **Area:** Finance persistence
- **Detected by:** User report
- **Symptom:** “Failed to save finance profile value.”
- **Root Cause:** Finance writes used non-service-role key and upsert conflict path was incomplete.
- **Fix:** Finance-specific auth headers + upsert conflict targeting + diagnostics.
- **Prevention:** Startup auth role diagnostics + env validation.
- **Status:** Closed

## INC-008 - Finance auth role unclear at runtime
- **Severity:** Medium
- **Area:** Observability
- **Detected by:** Debugging
- **Symptom:** Hard to tell which JWT role was active.
- **Root Cause:** No runtime auth-role visibility.
- **Fix:** Added startup finance auth role log.
- **Prevention:** Keep startup config sanity logs.
- **Status:** Closed

## INC-009 - Long text misrouted to Finance Profile
- **Severity:** High
- **Area:** Routing
- **Detected by:** User report
- **Symptom:** Long pasted docs triggered finance profile dashboard.
- **Root Cause:** Over-broad finance profile detector.
- **Fix:** Explicit phrase matching + long-text guard.
- **Prevention:** Route-priority tests with long documents.
- **Status:** Closed

## INC-010 - Memory intent ambiguity
- **Severity:** Medium
- **Area:** Memory UX
- **Detected by:** User report
- **Symptom:** Read/Remember/Save/Add-to-memory commands behaved inconsistently.
- **Root Cause:** No dedicated intent-state flow.
- **Fix:** Added `handle_memory_intent_flow` and explicit button-based save decisions.
- **Prevention:** Intent matrix tests by verb.
- **Status:** Closed

## INC-011 - “Read it” blocked by finance guard
- **Severity:** High
- **Area:** Memory/Finance interaction
- **Detected by:** User report
- **Symptom:** `Read it:` returned finance warning.
- **Root Cause:** Broad finance guard intercepted read flow.
- **Fix:** Read intent given priority; finance guard exempted for read flow.
- **Prevention:** Priority-order tests across handlers.
- **Status:** Closed

## INC-012 - Semantic memory pollution
- **Severity:** Medium
- **Area:** Memory quality
- **Detected by:** User report + data check
- **Symptom:** “You asked this before” on transient questions.
- **Root Cause:** Low-value question/command text stored/retrieved as memory.
- **Fix:** Write-time and retrieval-time filtering for low-value/transient content.
- **Prevention:** Memory quality filters + periodic memory audits.
- **Status:** Closed

## INC-013 - Document/insurance note blocked as finance-critical
- **Severity:** High
- **Area:** Memory save policy
- **Detected by:** User report
- **Symptom:** “Save as Document Note” blocked due to finance-like words.
- **Root Cause:** Content-only guard ignored memory source type.
- **Fix:** Source-aware policy:
  - block `finance/finance_memory`
  - allow `insurance/document_note/project_note/pdf`
  - keep guard for `personal_memory`.
- **Prevention:** Source-policy unit checks.
- **Status:** Closed

## INC-014 - Mixed personal + finance message blocked entirely
- **Severity:** High
- **Area:** Memory/Finance handling
- **Detected by:** User report
- **Symptom:** Entire mixed message blocked; safe personal facts lost.
- **Root Cause:** Early finance guard blocked whole payload.
- **Fix:** Mixed-content splitter:
  - saves safe personal facts
  - blocks finance profile lines
  - returns explicit “Saved / Not saved” response.
- **Prevention:** Mixed-input regression tests.
- **Status:** Closed
