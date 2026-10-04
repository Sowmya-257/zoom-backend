from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field, field_serializer
from app.schemas.user import UserResponse
from app.schemas.participant import ParticipantResponse


class MeetingBase(BaseModel):
    title: str = Field(default="Instant Meeting", max_length=255)
    description: Optional[str] = None
    duration_minutes: int = Field(default=30, ge=0)


class MeetingCreate(MeetingBase):
    host_id: Optional[str] = None
    waiting_room_enabled: Optional[bool] = False


class MeetingSchedule(MeetingBase):
    scheduled_time: Optional[datetime] = None
    scheduled_start_at: Optional[datetime] = None
    host_id: Optional[str] = None
    waiting_room_enabled: Optional[bool] = False


class MeetingUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    scheduled_start_at: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    status: Optional[str] = None
    waiting_room_enabled: Optional[bool] = None
    is_locked: Optional[bool] = None


class MeetingSecurityUpdate(BaseModel):
    waiting_room_enabled: Optional[bool] = None
    is_locked: Optional[bool] = None


class MeetingResponse(MeetingBase):
    id: str
    meeting_code: str
    room_name: str
    host_id: str
    host: Optional[UserResponse] = None
    scheduled_time: Optional[datetime] = None
    scheduled_start_at: Optional[datetime] = None
    status: str
    created_at: datetime
    started_at: Optional[datetime] = None
    actual_started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    actual_ended_at: Optional[datetime] = None
    actual_duration_minutes: Optional[int] = None
    waiting_room_enabled: bool = False
    is_locked: bool = False
    mute_new_participants: bool = False
    participant_count: int = 0
    shareable_url: Optional[str] = None

    @field_serializer(
        "created_at",
        "scheduled_time",
        "scheduled_start_at",
        "started_at",
        "actual_started_at",
        "ended_at",
        "actual_ended_at",
    )
    def serialize_dt(self, dt: Optional[datetime], _info):
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat()

    model_config = {"from_attributes": True}


class PaginatedMeetingResponse(BaseModel):
    items: List[MeetingResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class JoinMeetingRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    user_id: Optional[str] = None
    identity: Optional[str] = None
    is_host: Optional[bool] = None


class JoinMeetingResponse(BaseModel):
    meeting: MeetingResponse
    participant: ParticipantResponse
    token: Optional[str] = None
    livekit_url: str
    admission_status: str = "ADMITTED"


class JoinStatusResponse(BaseModel):
    admission_status: str
    token: Optional[str] = None
    livekit_url: str
    meeting: Optional[MeetingResponse] = None
