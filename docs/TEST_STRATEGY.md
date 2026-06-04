# Test Strategy (Phase A.5)

Last updated: 2026-06-04  
Status: Strategy only. Test framework implementation is next phase.

## Goals

- Prevent routing regressions in `handle_message`.
- Preserve finance safety guarantees.
- Preserve Gmail direct-routing behavior.
- Maintain deterministic identity answers.
- Keep memory quality high (no transient memory pollution).

## Test Layers

1. Golden prompt tests
- Input -> expected behavior keywords + expected service route.
- Stable guardrails for user-visible behavior.

2. Integration tests
- Supabase (mock/stub REST responses)
- Gmail API (mock Google client)
- Finance confirmation flow state transitions

3. Contract tests (future FastAPI)
- Endpoint request/response schema validation.

## Golden Prompt Set (Minimum 20)

1. `Who developed you?` -> identity answer includes Dhiraj Damare.
2. `Who owns you?` -> deterministic identity answer.
3. `most recent email from Supabase` -> Gmail API route, max_results=1.
4. `did I get an email from Advanzia` -> Gmail query with sender + fallback.
5. `search Gmail for invoice` -> Gmail search route.
6. `top 10 emails with subject invoice` -> subject query + count extraction.
7. `Read it: <long insurance text>` -> summarize only, no auto-save.
8. `Remember this: <note>` -> explicit memory save.
9. `Save this: <note>` -> explicit memory save.
10. `Add this to insurance memory: <content>` -> source=insurance save allowed.
11. `Add to finance memory: salary 2900` -> blocked, redirect to finance setup.
12. `Salary 2900 per month` -> no casual critical save, guided finance flow.
13. `My name is X, salary 2900` -> save personal facts, block salary line.
14. `Finance Setup` -> finance menu shown.
15. `Set Monthly Salary` then `2900` then `Save` -> confirmed profile write path.
16. `Save as Document Note` after `Read it` -> source=document_note save.
17. `System Status` -> dashboard formatted response.
18. `Show Errors` -> incident dashboard format.
19. `Draft Email` -> stepwise To/Subject/Body flow.
20. `Create Calendar Event` -> waiting state + real create call on next message.

## Finance-Specific Tests

- Amount parsing: `1,200`, `1.200`, `1,200.50`, `1.200,50`.
- Confirmation required before profile/goal/plan persistence.
- Cancel/edit flow clears pending state.
- No silent overwrite of salary/rent.

## Memory-Specific Tests

- Low-value command/question text not stored in semantic memory.
- Recall query should return facts, not repeated transient questions.
- Document and insurance sources remain storable even with money terms.

## Gmail-Specific Tests

- Intent parser coverage for from/subject/containing variants.
- No semantic-memory fallback for live Gmail questions.
- No-result message consistency.

## Identity Tests

- Creator/developer/owner/maintainer variants always resolve consistently.
- Never returns unapproved names.
