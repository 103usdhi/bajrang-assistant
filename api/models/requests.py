from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message text.")
    channel: str | None = Field(default="telegram", description="Source channel.")
    user_id: str | None = Field(default=None, description="External user identifier.")

