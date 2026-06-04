from pydantic import BaseModel


class ChatStubResponse(BaseModel):
    status: str
    request_id: str | None = None

