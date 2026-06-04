# API Contracts Draft (Phase B Target)

Last updated: 2026-06-04  
Status: Draft only. Endpoints not implemented yet.

## Common Conventions

- Base path: `/v1`
- Content type: `application/json`
- Time format: ISO-8601 UTC
- Error envelope:

```json
{
  "error": {
    "code": "string",
    "message": "string",
    "request_id": "req_xxx"
  }
}
```

Auth (target):
- Phase B internal: backend token or allowlisted origin.
- Phase C+: Google identity mapped to single owner account.

## POST /chat

Purpose: Main assistant entrypoint (replacement for Telegram direct orchestration).

Request:
```json
{
  "text": "most recent email from Supabase",
  "channel": "telegram",
  "user_id": "8106199737",
  "session_id": "optional",
  "metadata": {}
}
```

Response:
```json
{
  "reply": "Latest matching email ...",
  "actions": [],
  "request_id": "req_xxx"
}
```

Notes:
- Must preserve safe-confirmation behavior for external writes.
- Must preserve memory and finance guardrails.

## GET /memory/search

Purpose: Semantic memory retrieval.

Request (query params):
- `q` (required): search query
- `limit` (optional, default 5, max 20)

Response:
```json
{
  "query": "hansemerkur",
  "results": [
    {"content": "...", "source": "insurance", "created_at": "2026-06-01T10:20:00Z"}
  ],
  "request_id": "req_xxx"
}
```

Notes:
- Retrieval filters should suppress transient/low-value entries.

## GET /finance/profile

Purpose: Structured finance profile snapshot.

Request (query params):
- `include` optional: `commitments,goals,plans,upcoming`

Response:
```json
{
  "profile": {"monthly_salary": 2900, "monthly_rent": 1200, "currency": "EUR"},
  "commitments": [],
  "goals": [],
  "plans": [],
  "upcoming_obligations": [],
  "request_id": "req_xxx"
}
```

Notes:
- Read from finance tables only (not semantic memory).

## GET /gmail/search

Purpose: Execute Gmail search safely and return concise result metadata.

Request (query params):
- `q` required
- `max_results` optional (default 7, max 20)

Response:
```json
{
  "query": "from:Supabase -in:spam -in:trash",
  "count": 3,
  "emails": [
    {"from": "Supabase <noreply@supabase.com>", "subject": "...", "date": "...", "snippet": "..."}
  ],
  "request_id": "req_xxx"
}
```

Notes:
- Exclude spam/trash by default.
- Never log body/snippet content in detailed logs.

## POST /documents/analyze

Purpose: Analyze pasted text or uploaded document content and optionally prepare save actions.

Request:
```json
{
  "content": "Read it: ...",
  "mode": "summarize",
  "source": "document_note"
}
```

Response:
```json
{
  "summary": "Short summary...",
  "key_points": ["..."],
  "suggested_next_step": "...",
  "save_options": ["memory", "document_note", "no_save"],
  "request_id": "req_xxx"
}
```

Notes:
- `Read it` should never auto-save.
- Explicit save should remain source-aware.
