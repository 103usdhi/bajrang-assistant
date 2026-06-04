# Service Boundaries Mapping (bot.py -> Target Services)

Last updated: 2026-06-04  
Scope: Mapping only. No code moved yet.

## Mapping Table

| Function | Current Location | Target Service | Notes |
|---|---|---|---|
| `handle_message` | `bot.py` | `assistant_service` | Main orchestrator; too broad, should delegate only. |
| `build_live_context` | `bot.py` | `assistant_service` | Context assembly from providers. |
| `format_with_claude` | `bot.py` | `assistant_service` | LLM formatting helper. |
| `is_identity_question` | `bot.py` | `assistant_service` | Deterministic identity guard. |
| `handle_memory_intent_flow` | `bot.py` | `memory_service` | Stateful memory capture flow. |
| `save_semantic_memory` | `bot.py` | `memory_service` | Core semantic write path. |
| `search_semantic_memory` | `bot.py` | `memory_service` | Semantic retrieval path. |
| `should_store_semantic_memory` | `bot.py` | `memory_service` | Write filter policy. |
| `looks_like_low_value_memory_text` | `bot.py` | `memory_service` | Memory-quality filter. |
| `filter_semantic_results` | `bot.py` | `memory_service` | Retrieval quality filter. |
| `save_explicit_memory_content` | `bot.py` | `memory_service` | Source-aware explicit save. |
| `detect_memory_save_command` | `bot.py` | `memory_service` | Intent extraction for explicit save. |
| `detect_memory_recall_topic` | `bot.py` | `memory_service` | Recall intent extraction. |
| `format_memory_recall_response` | `bot.py` | `memory_service` | Response shaping for recall. |
| `summarize_read_request_content` | `bot.py` | `document_service` | Read/analyze pasted text pipeline. |
| `save_document_metadata` | `bot.py` | `document_service` | Uploaded document registry write. |
| `get_uploaded_documents` | `bot.py` | `document_service` | Document listing query. |
| `handle_document` | `bot.py` | `document_service` | Document ingest entrypoint (Telegram adapter today). |
| `get_documents_summary` | `bot.py` | `document_service` | Summary provider for command/live context. |
| `classify_finance_message` | `bot.py` | `finance_service` | Natural-language transaction parser. |
| `parse_finance_amount` | `bot.py` | `finance_service` | Locale-safe amount parser. |
| `is_critical_finance_capture_request` | `bot.py` | `finance_service` | Guard for profile-critical fields. |
| `save_financial_profile_values` | `bot.py` | `finance_service` | Service-role protected profile upsert. |
| `insert_financial_commitment` | `bot.py` | `finance_service` | Commitments insert. |
| `insert_financial_goal` | `bot.py` | `finance_service` | Goals insert. |
| `insert_financial_plan` | `bot.py` | `finance_service` | Plans insert. |
| `fetch_finance_rows` | `bot.py` | `finance_service` | Shared finance table fetcher. |
| `format_finance_profile_summary` | `bot.py` | `finance_service` | Dashboard response builder. |
| `handle_finance_foundation_flow` | `bot.py` | `finance_service` | Guided setup/confirm/edit/cancel flow. |
| `execute_finance_pending_action` | `bot.py` | `finance_service` | Save confirmation executor. |
| `parse_future_plan_text` | `bot.py` | `finance_service` | Future plan parser. |
| `parse_plan_month` | `bot.py` | `finance_service` | Month extraction logic. |
| `parse_gmail_search_intent` | `bot.py` | `gmail_service` | Gmail intent + query build entrypoint. |
| `search_gmail_messages` | `bot.py` | `gmail_service` | Gmail API search execution. |
| `get_gmail_summary` | `bot.py` | `gmail_service` | Summary and search proxy. |
| `format_gmail_search_results` | `bot.py` | `gmail_service` | Telegram-friendly Gmail output formatting. |
| `clean_gmail_snippet` | `bot.py` | `gmail_service` | Snippet sanitation pipeline. |
| `extract_gmail_result_count` | `bot.py` | `gmail_service` | Count extraction (`top 10`, etc.). |
| `get_google_credentials` | `bot.py` | `gmail_service` | Shared auth for Gmail/Calendar integrations. |
| `create_gmail_draft` | `bot.py` | `gmail_service` | Draft creation action. |
| `parse_calendar_event_request` | `bot.py` | `assistant_service` | Calendar intent parse (or future `calendar_service`). |
| `create_calendar_event_from_text` | `bot.py` | `assistant_service` | Calendar action execution. |
| `get_calendar_summary` | `bot.py` | `assistant_service` | Calendar read summary provider. |
| `get_asana_tasks` | `bot.py` | `assistant_service` | Asana read provider. |
| `create_asana_task` | `bot.py` | `assistant_service` | Asana write action. |
| `get_system_status` | `bot.py` | `assistant_service` | Cross-service health aggregation. |
| `format_system_status_dashboard` | `bot.py` | `assistant_service` | Status presentation formatter. |
| `log_system_error` | `bot.py` | `observability` | Central exception logging to `system_logs`. |
| `get_recent_system_errors` | `bot.py` | `observability` | Incident retrieval endpoint candidate. |
| `format_system_errors` | `bot.py` | `observability` | Incident dashboard formatter. |
| `send_clean_reply` | `bot.py` | `telegram_adapter` | Transport formatting/chunking boundary. |
| `clean_telegram_text` | `bot.py` | `telegram_adapter` | Telegram output normalization. |
| `split_telegram_chunks` | `bot.py` | `telegram_adapter` | Transport-level long message splitting. |
| `main` | `bot.py` | `telegram_adapter` | Runtime wiring and handler registration. |

## Boundary Recommendation

During Phase B extraction, keep adapters thin:

- Telegram adapter: parse inbound/update state only, call API.
- API layer: validate payloads, call services, return typed responses.
- Services: own business policy and data access.
