import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.participant import Participant, ParticipantRole
from app.models.meeting import Meeting, MeetingStatus
from app.models.meeting_event import MeetingEvent


class ParticipantService:
    @staticmethod
    def register_participant(
        db: Session,
        meeting: Meeting,
        display_name: str,
        identity: Optional[str] = None,
        user_id: Optional[str] = None,
        is_host: bool = False,
    ) -> Participant:
        """Register a participant joining a meeting with waiting room awareness."""
        if not identity:
            identity = f"user-{uuid.uuid4().hex[:8]}"

        role = ParticipantRole.HOST.value if is_host or (user_id and user_id == meeting.host_id) else ParticipantRole.PARTICIPANT.value

        # Check waiting room requirement
        is_host_user = (role == ParticipantRole.HOST.value)
        waiting_room = bool(getattr(meeting, "waiting_room_enabled", False))

        # Check existing participant
        participant = (
            db.query(Participant)
            .filter(
                Participant.meeting_id == meeting.id,
                Participant.identity == identity,
            )
            .first()
        )

        now = datetime.utcnow()
        if is_host_user:
            admission = "ADMITTED"
            waiting_since = None
        elif waiting_room:
            # If already admitted previously, keep ADMITTED; otherwise WAITING
            if participant and participant.admission_status == "ADMITTED":
                admission = "ADMITTED"
                waiting_since = None
            else:
                admission = "WAITING"
                waiting_since = now
        else:
            admission = "ADMITTED"
            waiting_since = None

        is_muted = bool(getattr(meeting, "mute_new_participants", False)) if not is_host_user else False

        if participant:
            participant.left_at = None
            participant.display_name = display_name
            participant.role = role
            participant.admission_status = admission
            if waiting_since:
                participant.waiting_since = waiting_since
            if is_muted:
                participant.is_muted = True
        else:
            participant = Participant(
                id=str(uuid.uuid4()),
                meeting_id=meeting.id,
                user_id=user_id,
                identity=identity,
                display_name=display_name,
                role=role,
                is_muted=is_muted,
                admission_status=admission,
                waiting_since=waiting_since,
                joined_at=now,
            )
            db.add(participant)

        # If host joined or participant was admitted, mark SCHEDULED -> ACTIVE
        if admission == "ADMITTED" and meeting.status == MeetingStatus.SCHEDULED.value:
            meeting.status = MeetingStatus.ACTIVE.value
            meeting.started_at = now
            meeting.actual_started_at = now

        event = MeetingEvent(
            meeting_id=meeting.id,
            event_type="PARTICIPANT_JOINED" if admission == "ADMITTED" else "PARTICIPANT_WAITING",
            data_json=f'{{"identity": "{identity}", "name": "{display_name}", "role": "{role}", "status": "{admission}"}}',
        )
        db.add(event)

        db.commit()
        db.refresh(participant)
        return participant

    @staticmethod
    def get_participant(db: Session, meeting_id: str, identity: str) -> Optional[Participant]:
        return (
            db.query(Participant)
            .filter(
                Participant.meeting_id == meeting_id,
                Participant.identity == identity,
            )
            .first()
        )

    @staticmethod
    def admit_participant(db: Session, meeting_id: str, identity: str) -> Optional[Participant]:
        participant = ParticipantService.get_participant(db, meeting_id, identity)
        if not participant:
            return None

        participant.admission_status = "ADMITTED"
        participant.waiting_since = None
        participant.left_at = None

        # Check if meeting needs to transition to ACTIVE
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if meeting and meeting.status == MeetingStatus.SCHEDULED.value:
            now = datetime.utcnow()
            meeting.status = MeetingStatus.ACTIVE.value
            meeting.started_at = now
            meeting.actual_started_at = now

        db.commit()
        db.refresh(participant)
        return participant

    @staticmethod
    def admit_all(db: Session, meeting_id: str) -> List[Participant]:
        waiting = (
            db.query(Participant)
            .filter(
                Participant.meeting_id == meeting_id,
                Participant.admission_status == "WAITING",
                Participant.left_at.is_(None),
            )
            .all()
        )
        now = datetime.utcnow()
        for p in waiting:
            p.admission_status = "ADMITTED"
            p.waiting_since = None
            p.left_at = None

        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if meeting and meeting.status == MeetingStatus.SCHEDULED.value:
            meeting.status = MeetingStatus.ACTIVE.value
            meeting.started_at = now
            meeting.actual_started_at = now

        db.commit()
        return waiting

    @staticmethod
    def remove_waiting(db: Session, meeting_id: str, identity: str) -> Optional[Participant]:
        participant = ParticipantService.get_participant(db, meeting_id, identity)
        if not participant:
            return None

        participant.admission_status = "REMOVED"
        participant.left_at = datetime.utcnow()
        db.commit()
        db.refresh(participant)
        return participant

    @staticmethod
    def list_waiting(db: Session, meeting_id: str) -> List[Participant]:
        return (
            db.query(Participant)
            .filter(
                Participant.meeting_id == meeting_id,
                Participant.admission_status == "WAITING",
                Participant.left_at.is_(None),
            )
            .all()
        )

    @staticmethod
    def leave_meeting(db: Session, meeting_id: str, identity: str) -> Optional[Participant]:
        participant = ParticipantService.get_participant(db, meeting_id, identity)
        if participant:
            participant.left_at = datetime.utcnow()
            event = MeetingEvent(
                meeting_id=meeting_id,
                event_type="PARTICIPANT_LEFT",
                data_json=f'{{"identity": "{identity}", "name": "{participant.display_name}"}}',
            )
            db.add(event)
            db.commit()
            db.refresh(participant)
        return participant

    @staticmethod
    def update_participant(
        db: Session,
        meeting_id: str,
        identity: str,
        is_muted: Optional[bool] = None,
        is_video_off: Optional[bool] = None,
    ) -> Optional[Participant]:
        participant = ParticipantService.get_participant(db, meeting_id, identity)
        if not participant:
            return None

        if is_muted is not None:
            participant.is_muted = is_muted
        if is_video_off is not None:
            participant.is_video_off = is_video_off

        db.commit()
        db.refresh(participant)
        return participant

    @staticmethod
    def list_active(db: Session, meeting_id: str) -> List[Participant]:
        return (
            db.query(Participant)
            .filter(
                Participant.meeting_id == meeting_id,
                Participant.left_at.is_(None),
                Participant.admission_status == "ADMITTED",
            )
            .all()
        )
