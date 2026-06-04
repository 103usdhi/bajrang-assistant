from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from api.middleware.request_id import RequestIDMiddleware
from api.routes.chat import router as chat_router
from api.routes.health import router as health_router

APP_VERSION = "phase-c1"

app = FastAPI(
    title="Bajrang API",
    version=APP_VERSION,
    description="Development-only FastAPI skeleton for future Telegram adapter extraction.",
)

app.add_middleware(RequestIDMiddleware)
app.include_router(health_router)
app.include_router(chat_router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "http_error",
                "message": exc.detail,
                "request_id": request_id,
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Internal server error",
                "request_id": request_id,
            }
        },
    )

