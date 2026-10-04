import enum
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Enum, Boolean
from sqlalchemy.orm import relationship
from app.database import Base


class MeetingStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"
    CANCELLED = "CANCELLED"


class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    meeting_code = Column(String(20), unique=True, index=True, nullable=False)  # e.g., "123-456-789"
    room_name = Column(String(100), unique=True, index=True, nullable=False)   # LiveKit room identifier
    title = Column(String(255), nullable=False, default="Instant Meeting")
    description = Column(Text, nullable=True)
    host_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    scheduled_time = Column(DateTime, nullable=True)
    scheduled_start_at = Column(DateTime, nullable=True)
    duration_minutes = Column(Integer, default=30, nullable=False)
    status = Column(String(20), default=MeetingStatus.SCHEDULED.value, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    actual_started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    actual_ended_at = Column(DateTime, nullable=True)
    waiting_room_enabled = Column(Boolean, default=False, nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False)
    mute_new_participants = Column(Boolean, default=False, nullable=False)

    host = relationship("User", back_populates="hosted_meetings")
    participants = relationship("Participant", back_populates="meeting", cascade="all, delete-orphan")
    events = relationship("MeetingEvent", back_populates="meeting", cascade="all, delete-orphan")
