from typing import Optional
from pydantic import BaseModel, Field


class TokenRequest(BaseModel):
    identity: Optional[str] = None
    display_name: str = Field(min_length=1, max_length=100)
    is_host: bool = False


class TokenResponse(BaseModel):
    token: str
    livekit_url: str
    room_name: str
    identity: str
