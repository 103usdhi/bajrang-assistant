# Bajrang Architecture (Phase A.5 Blueprint)

Last updated: 2026-06-04  
Scope: Documentation and planning only. No runtime refactor.

## Current Architecture

```text
Telegram
  -> bot.py (routing + business logic + integrations)
      -> Supabase (events_log, semantic_memory, finance, docs, system_logs)
      -> Claude / OpenAI
      -> Google APIs (Gmail, Calendar)
      -> Asana API
      -> Render/GitHub status APIs
```

## Current Responsibilities

- `bot.py` is both transport layer and domain layer.
- Telegram routing and state live in `handle_message()` and `context.user_data`.
- Data access is direct via `requests` calls to Supabase REST endpoints.
- External integrations are called directly from handlers.
- Logging is centralized via `log_system_error()` and persisted to `system_logs`.

## Target Architecture

```text
Telegram Client ----\
React Native App ----> FastAPI Gateway -> Bajrang Core
Web/CLI (future) ----/                     |
                                           +-> memory_service
                                           +-> finance_service
                                           +-> gmail_service
                                           +-> document_service
                                           +-> assistant_service
                                           +-> observability layer
```

## Service Boundaries (Target Intent)

- `assistant_service`: orchestration, intent routing, safety policy, response assembly.
- `memory_service`: semantic storage/retrieval, memory quality filtering, explicit memory saves.
- `finance_service`: profile/commitments/goals/plans, guarded writes, reporting.
- `gmail_service`: Gmail intent parsing, query generation, API search, formatting.
- `document_service`: upload metadata, PDF extraction/chunking hooks, document summaries.

## Dependency Boundaries

- Transport adapters (Telegram, future app) should not own business rules.
- Services should not depend on Telegram classes (`Update`, `ReplyKeyboardMarkup`).
- Supabase access should be behind service-level repository functions.
- Claude/OpenAI invocation should be centralized in assistant/document services.

## Future API Ownership

- FastAPI owns external contract (`/chat`, `/memory/*`, `/finance/*`, `/gmail/*`, `/documents/*`).
- Bajrang Core owns domain rules and integration calls.
- Client layers (Telegram/mobile) own UX only (menus, reply keyboard, local state visuals).

## Extraction Strategy (No Move Yet)

1. Freeze behavior using golden prompts.
2. Add thin service wrappers around existing functions in place.
3. Expose wrappers via FastAPI endpoints.
4. Convert Telegram handlers to API client calls.
5. Move implementation behind services incrementally after parity.
