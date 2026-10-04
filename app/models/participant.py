import enum
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class ParticipantRole(str, enum.Enum):
    HOST = "HOST"
    CO_HOST = "CO_HOST"
    PARTICIPANT = "PARTICIPANT"


class Participant(Base):
    __tablename__ = "participants"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    meeting_id = Column(String(36), ForeignKey("meetings.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    identity = Column(String(100), nullable=False)  # LiveKit participant identity
    display_name = Column(String(255), nullable=False)
    role = Column(String(20), default=ParticipantRole.PARTICIPANT.value, nullable=False)
    is_muted = Column(Boolean, default=False, nullable=False)
    is_video_off = Column(Boolean, default=False, nullable=False)
    admission_status = Column(String(20), default="ADMITTED", nullable=False)  # "ADMITTED", "WAITING", "REMOVED"
    waiting_since = Column(DateTime, nullable=True)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    left_at = Column(DateTime, nullable=True)

    meeting = relationship("Meeting", back_populates="participants")
    user = relationship("User", back_populates="participants")
