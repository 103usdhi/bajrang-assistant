# Bajrang Roadmap (v1.0)

**Status:** Approved & In Progress  
**Last Updated:** June 4, 2026  
**Next Gate:** Phase A.5 Foundation

---

## Phase A — Stabilization (Current)

**Goal:** No major bugs. Core features reliable.

**Must Complete:**
- ✅ Finance v1 (Salary parsing & tracking)
- ✅ Memory intent handling (Save/search/recall)
- ✅ Document Notes (Storage & retrieval)
- ✅ Gmail Intelligence (Search & parsing)
- ✅ Identity System (User context)

**Success Criteria:**
- [ ] Salary save/read works reliably
- [ ] Memory save/search works reliably
- [ ] Gmail search works reliably
- [ ] No major routing regressions
- [ ] All Phase A features tested manually

**Owner:** Current sprint

---

## Phase A.5 — Foundation (🚪 GATING PHASE)

**Goal:** Prepare Bajrang for app development. Transform from bot → platform.

**This is the single most important phase.** Do not skip or rush.

### 1. Service Boundaries

Define clear service layers with contracts:

```
memory_service      → Save/search memories, intent classification
finance_service     → Parse, store, report financial data
gmail_service       → Search, parse, retrieve Gmail data
document_service    → Store, retrieve, parse documents
assistant_service   → Orchestration, chat, routing
```

**Deliverable:** `docs/ARCHITECTURE.md` with service interfaces

### 2. Testing

- **Golden prompt tests (20+):** Define expected assistant responses for key scenarios
  - Example: "Tell me my spending this month" → parses finance, summarizes
  - Example: "Find emails about invoices" → Gmail search + context
  
- **Integration tests:** Supabase + Gmail mocks
  - Memory CRUD operations
  - Finance calculations
  - Gmail search without hitting real Gmail
  
- **Telegram tests:** Ensure no regressions

**Deliverable:** `tests/integration/` with 20+ passing tests, `tests/golden/`

### 3. Observability

- **Structured logging:** Every request gets a unique `request_id`
- **Error tracking:** Dashboard of failures (Sentry/custom)
- **Request tracing:** See the full path: Telegram → API → Services → DB

**Deliverable:** Logs with request IDs, error dashboard accessible

### 4. Security Documentation

Document every auth boundary:

- **Google OAuth:** Scope, token refresh, revocation
- **Gmail API:** Scopes used, data retention policy
- **Finance security:** PII handling, data masking
- **Supabase roles:** RLS policies, service role usage
- **Telegram Bot Token:** Secure storage, rotation plan

**Deliverable:** `docs/SECURITY.md` with audit trail

### 5. Documentation Structure

Create:

```
docs/
├── BAJRANG_VISION.md       (Why Bajrang exists)
├── BAJRANG_ROADMAP.md      (This file)
├── ARCHITECTURE.md         (Service design)
├── SECURITY.md             (Auth & data protection)
├── DECISIONS.md            (Why we chose X over Y)
├── INCIDENTS.md            (What broke and how we fixed it)
├── DEVELOPMENT.md          (Setup, run locally, deploy)
└── API.md                  (Endpoint reference)
```

**Deliverable:** Repo with complete docs

### Success Criteria

- [ ] 20+ golden tests passing
- [ ] Integration tests passing
- [ ] All services documented with interfaces
- [ ] Request tracing works end-to-end
- [ ] Security policies documented
- [ ] CI checks pass
- [ ] No manual steps to run tests

**Gate:** A.5 complete → unlock Phase B

---

## Phase B — API Extraction

**Goal:** Telegram becomes a client, not the owner.

**Build:**
- FastAPI service with typed endpoints
- Move all logic from `bot.py` → `core/`
- Telegram becomes a thin client

**Endpoints:**
```
POST   /chat                 → Send message, get response
GET    /memory/search        → Search memories
POST   /memory/save          → Save memory
GET    /finance/profile      → Get financial summary
GET    /gmail/search         → Search emails
GET    /documents/search     → Search documents
POST   /documents/upload     → Upload document
```

**Success Criteria:**
- [ ] Telegram uses API for all operations
- [ ] Existing functionality unchanged
- [ ] API can run standalone
- [ ] OpenAPI docs generated

**Owner:** After A.5

---

## Phase C — Bajrang App MVP

**Technology Stack:**
- React Native + Expo
- TypeScript
- Mobile-first design

**Features (Only these):**
- Google Sign-In (same account as Telegram user)
- Chat screen (Send/receive, memory search inline)
- Memory search (Find past interactions)
- Basic navigation

**What's NOT included:**
- ❌ Finance screen
- ❌ Gmail screen
- ❌ Documents screen
- ❌ Settings
- ❌ Voice
- ❌ Notifications

**Success Criteria:**
- [ ] Daily usable (no crashes for 5 min session)
- [ ] Google Sign-In works
- [ ] Chat works (same bot response)
- [ ] Memory search works

**Owner:** After Phase B

---

## Phase D — Personal AI OS

**Goal:** App becomes primary interface. Telegram optional.

**Add Screens:**
- Finance (Spending trends, salary tracking, insights)
- Documents (Stored docs, recent uploads)
- Gmail (Recent emails, search)
- Settings (Preferences, data management, logout)

**Success Criteria:**
- [ ] All 4 screens functional
- [ ] Data synced with Telegram bot
- [ ] App is primary daily driver

---

## Phase E — Advanced Features

**Add:**
- Voice input/output
- Push notifications
- Camera: Receipt/document scan
- Real-time typing indicators

**Owner:** After Phase D

---

## Security Model

### Do Build
✅ Single user account per install  
✅ Google Sign-In (OAuth 2.0)  
✅ Supabase Auth + RLS  
✅ Owner allowlist (only you + trusted)  
✅ Encrypted sensitive data (finance, PII)  

### Do NOT Build
❌ Public user registration  
❌ Multi-tenant SaaS  
❌ Subscription management  
❌ User administration panels  

**Rationale:** Bajrang is a personal AI OS, not a platform for others.

---

## Decision Log

**Why FastAPI and not X?**
- Typed, fast, good async support
- OpenAPI docs automatic
- Easy to test

**Why React Native and not Flutter?**
- TypeScript native
- Share logic with web (future)
- Expo for faster iteration

**Why this order?**
- A.5 forces good architecture early
- API extraction means app dev doesn't break Telegram
- App MVP keeps scope small

See `docs/DECISIONS.md` for full history.

---

## Immediate Next Steps

1. **Finish Phase A:** Ensure finance + memory are stable (current sprint)
2. **Start Phase A.5:** Create service boundaries document this week
3. **Create test structure:** Set up golden test framework
4. **Security audit:** Document auth policies
5. **Document everything:** Build the docs/ structure

---

## Timeline (Estimate)

| Phase   | Duration | Owner   |
|---------|----------|---------|
| A       | Done     | Current |
| A.5     | 2-3 wks  | You     |
| B       | 2-3 wks  | You     |
| C (MVP) | 3-4 wks  | You     |
| D       | 2 wks    | Future  |
| E       | Ongoing  | Future  |

---

## Success Metric

**Phase A.5 complete = Bajrang ready to scale**

At that point, adding new features doesn't create debt. The app dev, API extraction, and future work all rest on solid foundation.

🚀 **Approved. Let's build.**
