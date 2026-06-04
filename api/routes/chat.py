from fastapi import APIRouter, Request

from api.models.requests import ChatRequest
from api.models.responses import ChatStubResponse

router = APIRouter()


@router.post("/chat", response_model=ChatStubResponse)
def chat_stub(payload: ChatRequest, request: Request):
    _ = payload
    return ChatStubResponse(
        status="not_implemented",
        request_id=getattr(request.state, "request_id", None),
    )

