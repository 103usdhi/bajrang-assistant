# Telegram Adapter Inventory

Last updated: 2026-06-04  
Scope: Current Telegram-layer responsibilities and extraction boundaries.

## Purpose

Document what remains Telegram-specific in `bot.py` before extracting a thin adapter for FastAPI/Bajrang Core.

## Telegram-Only Responsibilities

- Telegram app bootstrap and handler registration (`main`)
- Telegram message/voice/document callback entrypoints
- Reply keyboard construction and menu text
- Callback query handling for read-aloud controls
- Telegram delivery concerns:
  - text cleaning for Telegram rendering
  - long-message chunking
  - reply markup attachment

## Primary Telegram Handlers

- `handle_message`
- `handle_voice`
- `handle_document`
- `handle_tts_callback`
- `handle_read_aloud`
- `handle_error`

## Update/Context Dependencies

- `Update` / `ContextTypes.DEFAULT_TYPE`
- `update.effective_user.id` allowlist checks
- `update.message`, `update.callback_query`, `reply_to_message`
- `context.user_data` for conversational state and flow progress

## Callback Handlers

- Inline callback for read-aloud button (`tts_read`)
- Text-command routing in `handle_message`
- Button routing via text labels (ReplyKeyboard-driven flows)

## Menus/Keyboard Surfaces

- Main menu
- Finance Setup submenu
- German A1 submenu
- Memory save decision keyboard
- Finance confirm/edit/cancel keyboard
- Read-aloud inline keyboard

## `context.user_data` State Usage (By Flow)

- Voice:
  - `voice_replies_enabled`

- Calendar:
  - `waiting_for_calendar_event`

- Email draft:
  - `waiting_for_email_to`
  - `waiting_for_email_subject`
  - `waiting_for_email_body`
  - `email_draft`

- Memory:
  - `waiting_for_read_it_content`
  - `waiting_for_memory_content`
  - `memory_capture_state`
  - `memory_pending_save_state`

- Finance:
  - `finance_flow_state`
  - `finance_pending_confirm`
  - `finance_edit_delete_state`

- German learning:
  - `waiting_for_german_word`
  - `waiting_for_german_meaning`
  - `waiting_for_german_example`
  - `german_word`
  - `waiting_for_grammar_topic`
  - `waiting_for_grammar_note`
  - `german_grammar`
  - `waiting_for_german_correction`
  - `waiting_for_german_quiz_answer`
  - `german_quiz`

## Future Adapter Boundaries

Target adapter responsibilities:
- Parse Telegram update into normalized inbound request
- Maintain Telegram UX artifacts (menus, keyboards, callback wiring)
- Forward normalized requests to core orchestration API/service
- Render final response text/voice/doc feedback back to Telegram

Move out of adapter (target core/services):
- intent and route policy
- business rules and safety guards
- external API calls (Gmail/Calendar/Asana)
- persistence and semantic memory operations
- cross-domain context assembly

## Extraction Notes

- Preserve current route order in `handle_message` until parity suite is in place.
- Keep `context.user_data` schema stable during adapter extraction.
- Prefer a feature-flagged dual path (in-process vs API) for migration safety.
