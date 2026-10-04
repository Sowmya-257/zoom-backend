from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, field_serializer


class ParticipantBase(BaseModel):
    display_name: str
    identity: Optional[str] = None
    role: str = "PARTICIPANT"
    is_muted: bool = False
    is_video_off: bool = False
    admission_status: str = "ADMITTED"


class ParticipantCreate(ParticipantBase):
    user_id: Optional[str] = None


class ParticipantUpdate(BaseModel):
    is_muted: Optional[bool] = None
    is_video_off: Optional[bool] = None
    role: Optional[str] = None
    admission_status: Optional[str] = None


class ParticipantResponse(ParticipantBase):
    id: str
    meeting_id: str
    user_id: Optional[str] = None
    identity: str
    joined_at: datetime
    left_at: Optional[datetime] = None
    waiting_since: Optional[datetime] = None

    @field_serializer("joined_at", "left_at", "waiting_since")
    def serialize_dt(self, dt: Optional[datetime], _info):
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat()

    model_config = {"from_attributes": True}
