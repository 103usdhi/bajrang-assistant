# Architecture Decisions (ADR)

Record: **Why we chose X over Y** so future us doesn't re-litigate.

---

## ADR-001: FastAPI for Bajrang Core

**Date:** June 4, 2026  
**Status:** Approved (Phase B)

**Decision:** Use FastAPI for the Bajrang Core service layer (Phase B).

**Alternatives:**
- Flask: Too minimal, no async
- Django: Too heavy, too much ORM magic
- Node.js: Could work, but Python is native

**Why FastAPI:**
- ✅ Native async/await
- ✅ Pydantic for type safety + validation
- ✅ OpenAPI docs automatic
- ✅ Python (consistency with bot.py)
- ✅ Fast (Starlette + uvicorn)
- ✅ Easy to test

**Trade-offs:**
- Smaller ecosystem than Django
- Need to pick ORM + deploy separately

**Impact:** All Phase B endpoints.

---

## ADR-002: Single-User, Not Multi-Tenant SaaS

**Date:** June 4, 2026  
**Status:** Approved

**Decision:** Bajrang is a personal AI OS for one user, not a platform.

**Alternatives:**
- Multi-tenant: Support many users
- Freemium SaaS: Free tier + paid tiers

**Why Single-User:**
- ✅ Simplifies auth (Google Sign-In only)
- ✅ Simplifies data isolation (no RLS nightmares)
- ✅ Simplifies deployment (single backend instance)
- ✅ Faster feature velocity (no admin panels)
- ✅ Better privacy (no user accounts database)

**Trade-offs:**
- Can't generate revenue directly
- Can't onboard friends (without duplicating setup)

**Impact:** Security model, app design, database schema.

---

## ADR-003: React Native + Expo (Not Native iOS/Android)

**Date:** June 4, 2026  
**Status:** Approved (Phase C)

**Decision:** Build app with React Native + Expo (not Swift + Kotlin).

**Alternatives:**
- Native (Swift + Kotlin): Faster, native feel
- Flutter: Dart, good performance
- React Native Bare: More control, more pain

**Why React Native + Expo:**
- ✅ TypeScript (same as Telegram bot logic)
- ✅ Share code with web (future web version)
- ✅ Expo simplifies deployment (no Xcode/Android Studio)
- ✅ Faster iteration
- ✅ Build once, iOS + Android

**Trade-offs:**
- Slightly slower than native
- Some native APIs require ejecting from Expo
- Less mature than Flutter

**Impact:** Phase C, Phase D.

---

## ADR-004: Supabase + Postgres (Not Firebase)

**Date:** June 4, 2026  
**Status:** Approved

**Decision:** Supabase (managed Postgres) for persistence.

**Alternatives:**
- Firebase (Firestore): Easy, but limited querying
- MongoDB: Document DB, less relational
- SQLite: Local-only, hard to sync

**Why Supabase:**
- ✅ SQL (powerful queries for analytics)
- ✅ RLS (row-level security for future multi-user)
- ✅ PostgREST API (auto-generated)
- ✅ Open source (not vendor lock-in)
- ✅ Good pricing

**Trade-offs:**
- Slightly more infrastructure than Firebase
- Need to understand SQL

**Impact:** All data storage, security model.

---

## ADR-005: Golden Tests Over Pure Unit Tests

**Date:** June 4, 2026  
**Status:** Approved (Phase A.5)

**Decision:** Prioritize golden tests (expected prompts/responses) over unit test coverage.

**Rationale:**
- Unit tests break during refactoring
- Golden tests validate user experience
- LLM outputs are non-deterministic (unit tests fail randomly)

**Golden Test Structure:**
```python
GOLDEN_TESTS = [
    {
        "input": "Tell me my spending this month",
        "expected_keywords": ["$X spent", "category breakdown"],
        "service_calls": ["finance_service.get_monthly_spending"]
    },
    {
        "input": "Find emails from my boss",
        "expected_keywords": ["boss@company.com", "N emails found"],
        "service_calls": ["gmail_service.search"]
    }
]
```

**Impact:** Phase A.5, CI/CD validation.

---

## ADR-006: Structured Logging with Request IDs (Not Print Statements)

**Date:** June 4, 2026  
**Status:** Approved (Phase A.5)

**Decision:** Every request gets a `request_id`. Logs are structured JSON.

**Example Log:**
```json
{
  "timestamp": "2026-06-04T10:30:45Z",
  "request_id": "req_abc123xyz",
  "service": "assistant_service",
  "action": "process_chat",
  "status": "success",
  "duration_ms": 250,
  "memory_search_count": 3
}
```

**Why:**
- ✅ Tracing end-to-end requests
- ✅ Debugging without SSH-ing
- ✅ Error correlation (all failures with same request_id)

**Trade-offs:**
- More verbose than print()
- Need log aggregation tool (CloudWatch, Datadog, etc.)

**Impact:** Phase A.5 onwards, all services.

---

## ADR-007: Google Sign-In Only (No Email/Password)

**Date:** June 4, 2026  
**Status:** Approved

**Decision:** Google OAuth only. No email/password registration.

**Why:**
- ✅ Single-user: Just click "Sign in with Google"
- ✅ No password management
- ✅ Gmail API scopes tied to same account
- ✅ Better UX

**Trade-offs:**
- Requires Google account
- No passwordless magic links

**Impact:** Auth flow, app login, security model.

---

## ADR-008: Telegram Remains Primary Until Phase C

**Date:** June 4, 2026  
**Status:** Approved

**Decision:** Telegram is the main interface until Phase C MVP is stable.

**Why:**
- ✅ Already works
- ✅ Doesn't block app development
- ✅ Reduces scope of Phase B

**When to switch:**
- Phase C app can do 80% of Telegram features
- User confirms they use app daily for a week

**Impact:** Timeline, rollout strategy.

---

**To Add:** Document decisions as you make them. This prevents re-debates.
