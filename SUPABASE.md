# Supabase & Persistence

## Schema Overview

- **`events_log`**: Flat log of every interaction. Used for short-term conversation context.
- **`personal_memory`**: Key-value style storage for explicit facts (e.g., "User prefers coffee").
- **`semantic_memory`**: Stores document chunks and message embeddings.
    - Columns: `id`, `content`, `embedding` (vector(1536)), `metadata`.
- **`uploaded_documents`**: Metadata for files uploaded via Telegram for RAG.
- **`expenses`**: Structured finance tracking.
- **`financial_profile`**: Critical monthly profile values (salary, rent).
- **`financial_commitments`**: Fixed monthly obligations (EMI/loan, recurring bills).
- **`financial_goals`**: Savings goals and target timelines.
- **`financial_plans`**: Planned future finance events (planned expense/investment/refund).

## Semantic Search Architecture

Bajrang uses OpenAI `text-embedding-3-small` for generating embeddings. Retrieval is performed using a Postgres function `match_documents` which computes cosine similarity.

## Health Monitoring

The bot checks database health by attempting a `count` operation on the `events_log` table.

**Important Note on Permissions:**
Finance Foundation v1 tables use service-role-only data access in this project.
`anon` and `authenticated` privileges are revoked for finance tables because they store sensitive personal finance data.
The bot uses server-side `service_role` access only for finance writes/reads.

## Maintenance

To clear conversation memory without deleting history, the bot uses a TTL or "window" logic in the `get_context` function rather than deleting rows.

## Finance Foundation v1

Critical finance data is intentionally write-protected behind guided confirmation flows in Telegram:
- Monthly salary
- Rent
- EMI / loan commitments
- Recurring bills
- Savings goals
- Future plans

These values are not auto-saved from casual chat text.
