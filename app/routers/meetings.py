import uuid
from typing import List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.meeting import Meeting, MeetingStatus
from app.models.participant import ParticipantRole
from app.schemas.meeting import (
    MeetingCreate,
    MeetingSchedule,
    MeetingUpdate,
    MeetingResponse,
    PaginatedMeetingResponse,
    MeetingSecurityUpdate,
    JoinMeetingRequest,
    JoinMeetingResponse,
    JoinStatusResponse,
)
from app.schemas.participant import ParticipantResponse
from app.schemas.token import TokenRequest, TokenResponse
from app.services.meeting_service import MeetingService
from app.services.participant_service import ParticipantService
from app.services.livekit_service import livekit_service

router = APIRouter(prefix="/api/meetings", tags=["Meetings"])


@router.post("", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
def create_instant_meeting(
    meeting_in: Optional[MeetingCreate] = None,
    db: Session = Depends(get_db),
):
    """Create an instant meeting immediately and return its code and URL."""
    meeting = MeetingService.create_instant_meeting(db, meeting_in)
    return MeetingService.format_meeting_response(meeting)


@router.post("/schedule", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
def schedule_meeting(
    schedule_in: MeetingSchedule,
    db: Session = Depends(get_db),
):
    """Schedule a meeting for a future date/time."""
    meeting = MeetingService.schedule_meeting(db, schedule_in)
    return MeetingService.format_meeting_response(meeting)


@router.get("/upcoming", response_model=List[MeetingResponse])
def get_upcoming_meetings(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Retrieve scheduled and active upcoming meetings."""
    meetings = MeetingService.list_upcoming(db, limit)
    return [MeetingService.format_meeting_response(m) for m in meetings]


@router.get("/recent")
def get_recent_meetings(
    page: Optional[int] = Query(None, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    limit: Optional[int] = Query(None, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Retrieve past ended meetings.
    If 'page' is provided, returns PaginatedMeetingResponse; otherwise returns List[MeetingResponse].
    """
    if page is not None:
        return MeetingService.list_recent_paginated(db, page=page, page_size=page_size)
    meetings = MeetingService.list_recent(db, limit=limit or 20)
    return [MeetingService.format_meeting_response(m) for m in meetings]


@router.get("", response_model=List[MeetingResponse])
def get_all_meetings(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List all meetings in descending order of creation."""
    meetings = MeetingService.list_all(db, limit)
    return [MeetingService.format_meeting_response(m) for m in meetings]


@router.get("/{meetingCode}", response_model=MeetingResponse)
def get_meeting(
    meetingCode: str,
    db: Session = Depends(get_db),
):
    """Validate and get meeting details by code, URL, or room name."""
    meeting = MeetingService.get_by_code(db, meetingCode)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting '{meetingCode}' not found. Please verify the meeting ID.",
        )
    return MeetingService.format_meeting_response(meeting)


@router.post("/{meetingCode}/join", response_model=JoinMeetingResponse)
def join_meeting(
    meetingCode: str,
    request: JoinMeetingRequest,
    db: Session = Depends(get_db),
):
    """
    Join a meeting: validates the meeting existence and status,
    checks waiting room / lock state, registers the participant,
    and returns either LiveKit WebRTC token (if admitted) or WAITING status.
    """
    meeting = MeetingService.get_by_code(db, meetingCode)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting '{meetingCode}' does not exist.",
        )

    if meeting.status == MeetingStatus.ENDED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This meeting has already ended.",
        )

    if meeting.status == MeetingStatus.CANCELLED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This meeting has been cancelled.",
        )

    # Determine identity and host status
    identity = request.identity or f"usr-{uuid.uuid4().hex[:8]}"
    active_parts = [
        p for p in meeting.participants
        if p.left_at is None and getattr(p, "admission_status", "ADMITTED") == "ADMITTED"
    ]

    if request.is_host is not None:
        is_host = request.is_host
    elif request.user_id and request.user_id == meeting.host_id:
        is_host = True
    elif len(active_parts) == 0:
        is_host = True
    else:
        is_host = False

    # Check lock
    if getattr(meeting, "is_locked", False) and not is_host:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This meeting has been locked by the host.",
        )

    participant = ParticipantService.register_participant(
        db=db,
        meeting=meeting,
        display_name=request.display_name.strip(),
        identity=identity,
        user_id=request.user_id,
        is_host=is_host,
    )

    admission = getattr(participant, "admission_status", "ADMITTED")

    # Generate token only if admitted
    token = None
    if admission == "ADMITTED":
        token = livekit_service.create_token(
            room_name=meeting.room_name,
            identity=identity,
            display_name=request.display_name.strip(),
            is_host=is_host,
        )

    return {
        "meeting": MeetingService.format_meeting_response(meeting),
        "participant": participant,
        "token": token,
        "livekit_url": livekit_service.livekit_url,
        "admission_status": admission,
    }


@router.get("/{meetingCode}/join-status", response_model=JoinStatusResponse)
def get_join_status(
    meetingCode: str,
    identity: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    Check if a waiting participant has been admitted by the host.
    If admitted, returns the signed LiveKit WebRTC access token.
    """
    meeting = MeetingService.get_by_code(db, meetingCode)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    participant = ParticipantService.get_participant(db, meeting.id, identity)
    if not participant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found")

    admission = getattr(participant, "admission_status", "ADMITTED")
    token = None
    if admission == "ADMITTED":
        token = livekit_service.create_token(
            room_name=meeting.room_name,
            identity=identity,
            display_name=participant.display_name,
            is_host=(participant.role == ParticipantRole.HOST.value),
        )

    return {
        "admission_status": admission,
        "token": token,
        "livekit_url": livekit_service.livekit_url,
        "meeting": MeetingService.format_meeting_response(meeting),
    }


@router.get("/{meetingCode}/waiting-participants", response_model=List[ParticipantResponse])
def get_waiting_participants(
    meetingCode: str,
    db: Session = Depends(get_db),
):
    """Host action: list participants currently in the waiting room."""
    meeting = MeetingService.get_by_code(db, meetingCode)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    return ParticipantService.list_waiting(db, meeting.id)


@router.post("/{meetingCode}/participants/{identity}/admit")
def admit_participant(
    meetingCode: str,
    identity: str,
    db: Session = Depends(get_db),
):
    """Host action: admit a waiting participant into the meeting."""
    meeting = MeetingService.get_by_code(db, meetingCode)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    participant = ParticipantService.admit_participant(db, meeting.id, identity)
    if not participant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found")

    return {"status": "admitted", "identity": identity}


@router.post("/{meetingCode}/admit-all")
def admit_all_participants(
    meetingCode: str,
    db: Session = Depends(get_db),
):
    """Host action: admit all waiting participants into the meeting."""
    meeting = MeetingService.get_by_code(db, meetingCode)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    admitted = ParticipantService.admit_all(db, meeting.id)
    return {"status": "all_admitted", "count": len(admitted)}


@router.patch("/{meetingCode}/security", response_model=MeetingResponse)
def update_meeting_security(
    meetingCode: str,
    security_in: MeetingSecurityUpdate,
    db: Session = Depends(get_db),
):
    """Host action: toggle waiting room or lock status."""
    meeting = MeetingService.update_security(
        db,
        meetingCode,
        waiting_room_enabled=security_in.waiting_room_enabled,
        is_locked=security_in.is_locked,
    )
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    return MeetingService.format_meeting_response(meeting)


@router.post("/{meetingCode}/mute-all")
def mute_all_participants(
    meetingCode: str,
    db: Session = Depends(get_db),
):
    """Host action: mark mute on all participants and set mute for subsequent joiners."""
    meeting = MeetingService.set_mute_all(db, meetingCode)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    return {"status": "muted_all"}


@router.post("/{meetingCode}/token", response_model=TokenResponse)
def get_meeting_token(
    meetingCode: str,
    request: TokenRequest,
    db: Session = Depends(get_db),
):
    """Generate a LiveKit participant token for an existing meeting."""
    meeting = MeetingService.get_by_code(db, meetingCode)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting '{meetingCode}' not found.",
        )

    if meeting.status == MeetingStatus.ENDED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This meeting has already ended.",
        )

    identity = request.identity or f"usr-{uuid.uuid4().hex[:8]}"
    token = livekit_service.create_token(
        room_name=meeting.room_name,
        identity=identity,
        display_name=request.display_name.strip(),
        is_host=request.is_host,
    )

    return {
        "token": token,
        "livekit_url": livekit_service.livekit_url,
        "room_name": meeting.room_name,
        "identity": identity,
    }


@router.post("/{meetingCode}/end", response_model=MeetingResponse)
async def end_meeting(
    meetingCode: str,
    db: Session = Depends(get_db),
):
    """End a meeting for all participants."""
    meeting = MeetingService.end_meeting(db, meetingCode)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting '{meetingCode}' not found.",
        )
    # Terminate LiveKit room and disconnect all participants
    try:
        await livekit_service.delete_room(meeting.room_name)
    except Exception as e:
        logger.error(f"Error terminating LiveKit room {meeting.room_name}: {e}")

    return MeetingService.format_meeting_response(meeting)


@router.post("/{meetingCode}/leave")
def leave_meeting(
    meetingCode: str,
    identity: str = Query(...),
    db: Session = Depends(get_db),
):
    """Record participant departure from a meeting."""
    meeting = MeetingService.get_by_code(db, meetingCode)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    ParticipantService.leave_meeting(db, meeting.id, identity)
    return {"status": "left"}


@router.get("/{meetingCode}/participants", response_model=List[ParticipantResponse])
def get_participants(
    meetingCode: str,
    db: Session = Depends(get_db),
):
    """List all currently active admitted participants in a meeting."""
    meeting = MeetingService.get_by_code(db, meetingCode)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    participants = ParticipantService.list_active(db, meeting.id)
    return participants


@router.post("/{meetingCode}/participants/{identity}/remove")
async def remove_participant(
    meetingCode: str,
    identity: str,
    db: Session = Depends(get_db),
):
    """Host action: remove a participant from the meeting / waiting room and LiveKit room."""
    meeting = MeetingService.get_by_code(db, meetingCode)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    participant = ParticipantService.get_participant(db, meeting.id, identity)
    if participant and participant.admission_status == "WAITING":
        ParticipantService.remove_waiting(db, meeting.id, identity)
        return {"status": "removed", "identity": identity}

    # If connected to LiveKit server, disconnect them
    try:
        await livekit_service.remove_participant(meeting.room_name, identity)
    except Exception as e:
        print(f"[LiveKit remove note]: {e}")

    ParticipantService.leave_meeting(db, meeting.id, identity)
    if participant:
        participant.admission_status = "REMOVED"
        db.commit()

    return {"status": "removed", "identity": identity}


@router.put("/{meetingId}", response_model=MeetingResponse)
def update_meeting(
    meetingId: str,
    meeting_update: MeetingUpdate,
    db: Session = Depends(get_db),
):
    """Update meeting details."""
    meeting = MeetingService.update_meeting(db, meetingId, meeting_update)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    return MeetingService.format_meeting_response(meeting)


@router.delete("/{meetingId}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting(
    meetingId: str,
    db: Session = Depends(get_db),
):
    """Delete a meeting."""
    deleted = MeetingService.delete_meeting(db, meetingId)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    return None
