import math
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, asc

from app.models.meeting import Meeting, MeetingStatus
from app.models.user import User
from app.models.participant import Participant, ParticipantRole
from app.models.meeting_event import MeetingEvent
from app.schemas.meeting import MeetingCreate, MeetingSchedule, MeetingUpdate
from app.utils.code_generator import generate_meeting_code, normalize_meeting_code
from app.config import settings


class MeetingService:
    @staticmethod
    def get_or_create_default_user(db: Session) -> User:
        """Fetch default user or create one for seeded/instant hosting."""
        user = db.query(User).filter(User.email == "host@zoom-scaler.com").first()
        if not user:
            user = User(
                id=str(uuid.uuid4()),
                email="host@zoom-scaler.com",
                full_name="Alex Morgan",
                avatar_url="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

    @staticmethod
    def _generate_unique_code(db: Session) -> str:
        """Generate a guaranteed unique meeting code."""
        while True:
            code = generate_meeting_code()
            existing = db.query(Meeting).filter(Meeting.meeting_code == code).first()
            if not existing:
                return code

    @staticmethod
    def format_meeting_response(meeting: Meeting) -> dict:
        """Format a meeting model into response dictionary with helper fields."""
        active_participants = [
            p for p in meeting.participants
            if p.left_at is None and getattr(p, "admission_status", "ADMITTED") == "ADMITTED"
        ]

        actual_started = meeting.actual_started_at or meeting.started_at
        actual_ended = meeting.actual_ended_at or meeting.ended_at
        sched_time = meeting.scheduled_start_at or meeting.scheduled_time

        # Precise duration calculation
        if meeting.status == MeetingStatus.ENDED.value:
            if actual_ended and actual_started:
                duration = max(0, int((actual_ended - actual_started).total_seconds() / 60))
            else:
                duration = 0
        elif meeting.status == MeetingStatus.ACTIVE.value and actual_started:
            duration = max(0, int((datetime.utcnow() - actual_started).total_seconds() / 60))
        else:
            duration = meeting.duration_minutes or 30

        return {
            "id": meeting.id,
            "meeting_code": meeting.meeting_code,
            "room_name": meeting.room_name,
            "title": meeting.title,
            "description": meeting.description,
            "host_id": meeting.host_id,
            "host": meeting.host,
            "scheduled_time": sched_time,
            "scheduled_start_at": sched_time,
            "duration_minutes": duration,
            "actual_duration_minutes": duration,
            "status": meeting.status,
            "created_at": meeting.created_at,
            "started_at": actual_started,
            "actual_started_at": actual_started,
            "ended_at": actual_ended,
            "actual_ended_at": actual_ended,
            "waiting_room_enabled": bool(getattr(meeting, "waiting_room_enabled", False)),
            "is_locked": bool(getattr(meeting, "is_locked", False)),
            "mute_new_participants": bool(getattr(meeting, "mute_new_participants", False)),
            "participant_count": len(active_participants),
            "shareable_url": f"{settings.FRONTEND_URL}/meeting/{meeting.meeting_code}",
        }

    @classmethod
    def create_instant_meeting(
        cls,
        db: Session,
        meeting_data: Optional[MeetingCreate] = None,
    ) -> Meeting:
        """Create an active instant meeting immediately."""
        host = cls.get_or_create_default_user(db)
        host_id = meeting_data.host_id if (meeting_data and meeting_data.host_id) else host.id

        code = cls._generate_unique_code(db)
        room_name = f"room-{uuid.uuid4().hex[:12]}"
        title = meeting_data.title if (meeting_data and meeting_data.title) else "Instant Meeting"
        description = meeting_data.description if meeting_data else None
        duration = meeting_data.duration_minutes if meeting_data else 30
        waiting_room = meeting_data.waiting_room_enabled if meeting_data else False

        now = datetime.utcnow()
        meeting = Meeting(
            id=str(uuid.uuid4()),
            meeting_code=code,
            room_name=room_name,
            title=title,
            description=description,
            host_id=host_id,
            scheduled_time=None,
            scheduled_start_at=None,
            duration_minutes=duration,
            status=MeetingStatus.ACTIVE.value,
            created_at=now,
            started_at=now,
            actual_started_at=now,
            waiting_room_enabled=waiting_room,
            is_locked=False,
            mute_new_participants=False,
        )
        db.add(meeting)

        event = MeetingEvent(
            meeting_id=meeting.id,
            event_type="MEETING_CREATED",
            data_json=f'{{"title": "{title}", "type": "INSTANT"}}',
        )
        db.add(event)

        db.commit()
        db.refresh(meeting)
        return meeting

    @classmethod
    def schedule_meeting(
        cls,
        db: Session,
        schedule_data: MeetingSchedule,
    ) -> Meeting:
        """Schedule a meeting for a future date/time."""
        host = cls.get_or_create_default_user(db)
        host_id = schedule_data.host_id if schedule_data.host_id else host.id

        code = cls._generate_unique_code(db)
        room_name = f"room-{uuid.uuid4().hex[:12]}"

        # Canonicalize scheduled time into UTC
        sched_time = schedule_data.scheduled_start_at or schedule_data.scheduled_time
        if sched_time:
            if sched_time.tzinfo is not None:
                sched_time = sched_time.astimezone(timezone.utc).replace(tzinfo=None)

        now = datetime.utcnow()
        waiting_room = schedule_data.waiting_room_enabled or False

        meeting = Meeting(
            id=str(uuid.uuid4()),
            meeting_code=code,
            room_name=room_name,
            title=schedule_data.title,
            description=schedule_data.description,
            host_id=host_id,
            scheduled_time=sched_time,
            scheduled_start_at=sched_time,
            duration_minutes=schedule_data.duration_minutes,
            status=MeetingStatus.SCHEDULED.value,
            created_at=now,
            started_at=None,
            actual_started_at=None,
            waiting_room_enabled=waiting_room,
            is_locked=False,
            mute_new_participants=False,
        )
        db.add(meeting)

        event = MeetingEvent(
            meeting_id=meeting.id,
            event_type="MEETING_SCHEDULED",
            data_json=f'{{"title": "{schedule_data.title}", "scheduled_time": "{sched_time.isoformat() if sched_time else ""}"}}',
        )
        db.add(event)

        db.commit()
        db.refresh(meeting)
        return meeting

    @classmethod
    def get_by_code(cls, db: Session, code_or_input: str) -> Optional[Meeting]:
        """Look up meeting by code, URL, or room name."""
        normalized = normalize_meeting_code(code_or_input)
        raw_clean = code_or_input.strip()

        meeting = (
            db.query(Meeting)
            .filter(
                or_(
                    Meeting.meeting_code == normalized,
                    Meeting.meeting_code == raw_clean,
                    Meeting.room_name == raw_clean,
                    Meeting.id == raw_clean,
                )
            )
            .first()
        )
        return meeting

    @classmethod
    def get_by_id(cls, db: Session, meeting_id: str) -> Optional[Meeting]:
        return db.query(Meeting).filter(Meeting.id == meeting_id).first()

    @classmethod
    def list_upcoming(cls, db: Session, limit: int = 20) -> List[Meeting]:
        """List meetings that are SCHEDULED or ACTIVE with future or recent start times."""
        meetings = (
            db.query(Meeting)
            .filter(
                or_(
                    Meeting.status == MeetingStatus.SCHEDULED.value,
                    Meeting.status == MeetingStatus.ACTIVE.value,
                )
            )
            .order_by(
                Meeting.scheduled_time.asc().nulls_last(),
                Meeting.created_at.desc(),
            )
            .limit(limit)
            .all()
        )
        return meetings

    @classmethod
    def list_recent(cls, db: Session, limit: int = 20) -> List[Meeting]:
        """List meetings that have ENDED or are past."""
        meetings = (
            db.query(Meeting)
            .filter(
                or_(
                    Meeting.status == MeetingStatus.ENDED.value,
                    Meeting.status == MeetingStatus.CANCELLED.value,
                )
            )
            .order_by(desc(Meeting.ended_at), desc(Meeting.created_at))
            .limit(limit)
            .all()
        )
        return meetings

    @classmethod
    def list_recent_paginated(
        cls, db: Session, page: int = 1, page_size: int = 10
    ) -> Dict[str, Any]:
        """Paginated list of recent ended meetings."""
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 10

        query = (
            db.query(Meeting)
            .filter(
                or_(
                    Meeting.status == MeetingStatus.ENDED.value,
                    Meeting.status == MeetingStatus.CANCELLED.value,
                )
            )
            .order_by(desc(Meeting.ended_at), desc(Meeting.created_at))
        )
        total = query.count()
        total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1
        items = query.offset((page - 1) * page_size).limit(page_size).all()

        return {
            "items": [cls.format_meeting_response(m) for m in items],
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        }

    @classmethod
    def list_all(cls, db: Session, limit: int = 50) -> List[Meeting]:
        return (
            db.query(Meeting)
            .order_by(desc(Meeting.created_at))
            .limit(limit)
            .all()
        )

    @classmethod
    def update_meeting(cls, db: Session, meeting_id: str, updates: MeetingUpdate) -> Optional[Meeting]:
        meeting = cls.get_by_id(db, meeting_id)
        if not meeting:
            return None

        update_dict = updates.dict(exclude_unset=True)
        for key, val in update_dict.items():
            if hasattr(meeting, key):
                setattr(meeting, key, val)

        if updates.status == MeetingStatus.ENDED.value and not meeting.ended_at:
            now = datetime.utcnow()
            meeting.ended_at = now
            meeting.actual_ended_at = now
            if meeting.actual_started_at:
                meeting.duration_minutes = max(0, int((now - meeting.actual_started_at).total_seconds() / 60))

        db.commit()
        db.refresh(meeting)
        return meeting

    @classmethod
    def update_security(
        cls,
        db: Session,
        meeting_code: str,
        waiting_room_enabled: Optional[bool] = None,
        is_locked: Optional[bool] = None,
    ) -> Optional[Meeting]:
        meeting = cls.get_by_code(db, meeting_code)
        if not meeting:
            return None

        if waiting_room_enabled is not None:
            meeting.waiting_room_enabled = waiting_room_enabled
        if is_locked is not None:
            meeting.is_locked = is_locked

        db.commit()
        db.refresh(meeting)
        return meeting

    @classmethod
    def set_mute_all(cls, db: Session, meeting_code: str) -> Optional[Meeting]:
        meeting = cls.get_by_code(db, meeting_code)
        if not meeting:
            return None

        meeting.mute_new_participants = True
        # Mute active non-host participants in DB
        for p in meeting.participants:
            if p.left_at is None and p.role != ParticipantRole.HOST.value:
                p.is_muted = True

        db.commit()
        db.refresh(meeting)
        return meeting

    @classmethod
    def delete_meeting(cls, db: Session, meeting_id: str) -> bool:
        meeting = cls.get_by_id(db, meeting_id)
        if not meeting:
            return False
        db.delete(meeting)
        db.commit()
        return True

    @classmethod
    def end_meeting(cls, db: Session, meeting_code: str) -> Optional[Meeting]:
        meeting = cls.get_by_code(db, meeting_code)
        if not meeting:
            return None

        now = datetime.utcnow()
        meeting.status = MeetingStatus.ENDED.value
        meeting.ended_at = now
        meeting.actual_ended_at = now

        started = meeting.actual_started_at or meeting.started_at
        if started:
            meeting.duration_minutes = max(0, int((now - started).total_seconds() / 60))
        else:
            meeting.duration_minutes = 0

        event = MeetingEvent(
            meeting_id=meeting.id,
            event_type="MEETING_ENDED",
            data_json=f'{{"ended_at": "{now.isoformat()}", "duration": {meeting.duration_minutes}}}',
        )
        db.add(event)

        # Mark any remaining active participants as left
        for p in meeting.participants:
            if p.left_at is None:
                p.left_at = now

        db.commit()
        db.refresh(meeting)
        return meeting
