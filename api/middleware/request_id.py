import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        logging.info("api_request path=%s method=%s request_id=%s", request.url.path, request.method, request_id)
        return response

