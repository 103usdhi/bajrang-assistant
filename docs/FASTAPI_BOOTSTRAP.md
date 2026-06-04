# FastAPI Bootstrap (Phase C.1)

Last updated: 2026-06-04  
Status: Development-only infrastructure. Telegram remains primary.

## Purpose

Introduce a minimal FastAPI skeleton without changing production Telegram behavior.

## Startup Flow

1. Start app: `uvicorn api.main:app --host 127.0.0.1 --port 8000`
2. Request-ID middleware runs first:
   - reads `x-request-id` header if provided
   - otherwise generates a UUID
   - stores ID in `request.state.request_id`
   - appends ID to response header
3. Route handler executes.
4. Any error response includes `request_id`.

## Routes

- `GET /health`
  - Response:
    - `{"status":"ok","version":"phase-c1"}`

- `POST /chat`
  - Request model only (no business logic yet)
  - Stub response:
    - `{"status":"not_implemented","request_id":"..."}`

## Middleware

- `api/middleware/request_id.py`
  - Correlation/request ID generation
  - Request-state attachment
  - Response header propagation
  - Basic structured request log line

## Models

- `api/models/requests.py`
  - `ChatRequest`
- `api/models/responses.py`
  - `ChatStubResponse`

## Error Handling

Defined in `api/main.py`:
- HTTP errors -> envelope with `request_id`
- Unhandled errors -> generic internal error envelope with `request_id`

## Future Service Integration (Next Phases)

- `/chat` will call assistant orchestration service.
- Additional endpoints will map to memory, finance, Gmail, and documents services.
- Telegram adapter will become a thin client against this API.
- No production cutover until parity/regression checks pass.
