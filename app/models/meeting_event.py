import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base


class MeetingEvent(Base):
    __tablename__ = "meeting_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    meeting_id = Column(String(36), ForeignKey("meetings.id"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)  # CREATED, STARTED, ENDED, PARTICIPANT_JOINED, PARTICIPANT_LEFT, MUTE_ALL
    data_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    meeting = relationship("Meeting", back_populates="events")
