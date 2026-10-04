import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "database" in data
    assert data["database"] == "connected"


def test_create_instant_meeting():
    response = client.post("/api/meetings", json={"title": "Test Instant Meeting"})
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Instant Meeting"
    assert "meeting_code" in data
    assert len(data["meeting_code"]) >= 9
    assert data["status"] == "ACTIVE"
    assert "shareable_url" in data


def test_get_meeting_by_code():
    # First create
    create_res = client.post("/api/meetings", json={"title": "Meeting To Find"})
    meeting_code = create_res.json()["meeting_code"]

    # Now get
    get_res = client.get(f"/api/meetings/{meeting_code}")
    assert get_res.status_code == 200
    assert get_res.json()["meeting_code"] == meeting_code
    assert get_res.json()["title"] == "Meeting To Find"


def test_get_nonexistent_meeting():
    response = client.get("/api/meetings/999-999-999")
    assert response.status_code == 404


def test_schedule_meeting():
    scheduled_time = (datetime.utcnow() + timedelta(days=3)).isoformat()
    payload = {
        "title": "Quarterly Planning Sync",
        "description": "Discussing next quarter OKRs",
        "scheduled_time": scheduled_time,
        "duration_minutes": 60,
    }
    response = client.post("/api/meetings/schedule", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Quarterly Planning Sync"
    assert data["status"] == "SCHEDULED"
    assert data["duration_minutes"] == 60


def test_list_upcoming_and_recent_meetings():
    upcoming_res = client.get("/api/meetings/upcoming")
    assert upcoming_res.status_code == 200
    assert isinstance(upcoming_res.json(), list)

    recent_res = client.get("/api/meetings/recent")
    assert recent_res.status_code == 200
    assert isinstance(recent_res.json(), list)


def test_join_meeting_and_get_token():
    # Create meeting
    create_res = client.post("/api/meetings", json={"title": "Join Test Room"})
    code = create_res.json()["meeting_code"]

    # Join meeting
    join_res = client.post(
        f"/api/meetings/{code}/join",
        json={"display_name": "Test Participant"},
    )
    assert join_res.status_code == 200
    join_data = join_res.json()
    assert "token" in join_data
    assert len(join_data["token"]) > 20
    assert join_data["participant"]["display_name"] == "Test Participant"
    assert "livekit_url" in join_data


def test_end_meeting():
    create_res = client.post("/api/meetings", json={"title": "Room To End"})
    code = create_res.json()["meeting_code"]

    end_res = client.post(f"/api/meetings/{code}/end")
    assert end_res.status_code == 200
    assert end_res.json()["status"] == "ENDED"

    # Joining ended meeting should fail with 400
    join_res = client.post(
        f"/api/meetings/{code}/join",
        json={"display_name": "Late Person"},
    )
    assert join_res.status_code == 400
    assert "already ended" in join_res.json()["detail"].lower()


def test_meeting_time_accuracy_and_duration():
    # 1. Create instant meeting
    res = client.post("/api/meetings", json={"title": "Timing Precision Test"})
    assert res.status_code == 201
    data = res.json()
    code = data["meeting_code"]

    assert data["actual_started_at"] is not None
    assert "Z" in data["actual_started_at"] or "+00:00" in data["actual_started_at"]

    # 2. End meeting
    end_res = client.post(f"/api/meetings/{code}/end")
    assert end_res.status_code == 200
    end_data = end_res.json()
    assert end_data["actual_ended_at"] is not None
    assert "Z" in end_data["actual_ended_at"] or "+00:00" in end_data["actual_ended_at"]
    assert end_data["duration_minutes"] >= 0


def test_scheduled_meeting_timezone_canonicalization():
    target_utc_str = "2026-10-05T13:00:00Z"
    payload = {
        "title": "Timezone Preservation Test",
        "scheduled_time": target_utc_str,
        "duration_minutes": 45,
    }
    res = client.post("/api/meetings/schedule", json=payload)
    assert res.status_code == 201
    data = res.json()

    # Verify that scheduled_time returned by API ends with Z / timezone indicator
    assert data["scheduled_time"] is not None
    assert "Z" in data["scheduled_time"] or "+00:00" in data["scheduled_time"]
    assert "2026-10-05T13:00:00" in data["scheduled_time"]


def test_recent_meetings_pagination():
    res = client.get("/api/meetings/recent?page=1&page_size=3")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "page" in data
    assert data["page"] == 1
    assert "page_size" in data
    assert data["page_size"] == 3
    assert "total" in data
    assert "total_pages" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) <= 3


def test_waiting_room_flow_and_host_controls():
    # 1. Schedule a meeting with waiting room enabled
    sched_time = (datetime.utcnow() + timedelta(hours=2)).isoformat() + "Z"
    res = client.post(
        "/api/meetings/schedule",
        json={
            "title": "Waiting Room Test Meeting",
            "scheduled_time": sched_time,
            "duration_minutes": 30,
            "waiting_room_enabled": True,
        },
    )
    assert res.status_code == 201
    meeting = res.json()
    code = meeting["meeting_code"]
    assert meeting["waiting_room_enabled"] is True

    # 2. Host joins first
    host_res = client.post(
        f"/api/meetings/{code}/join",
        json={"display_name": "Host Alice", "is_host": True, "identity": "host-alice-1"},
    )
    assert host_res.status_code == 200
    host_data = host_res.json()
    assert host_data["admission_status"] == "ADMITTED"
    assert host_data["token"] is not None

    # Meeting should now be ACTIVE
    get_m = client.get(f"/api/meetings/{code}").json()
    assert get_m["status"] == "ACTIVE"
    assert get_m["actual_started_at"] is not None

    # 3. Participant Bob joins with waiting room enabled
    bob_res = client.post(
        f"/api/meetings/{code}/join",
        json={"display_name": "Guest Bob", "is_host": False, "identity": "guest-bob-2"},
    )
    assert bob_res.status_code == 200
    bob_data = bob_res.json()
    assert bob_data["admission_status"] == "WAITING"
    assert bob_data["token"] is None  # Token withheld until admitted!

    # 4. Host views waiting participants list
    waiting_res = client.get(f"/api/meetings/{code}/waiting-participants")
    assert waiting_res.status_code == 200
    waiting_list = waiting_res.json()
    assert any(p["identity"] == "guest-bob-2" for p in waiting_list)

    # 5. Bob polls join-status while waiting
    bob_status_1 = client.get(f"/api/meetings/{code}/join-status?identity=guest-bob-2").json()
    assert bob_status_1["admission_status"] == "WAITING"
    assert bob_status_1["token"] is None

    # 6. Host admits Bob
    admit_res = client.post(f"/api/meetings/{code}/participants/guest-bob-2/admit")
    assert admit_res.status_code == 200
    assert admit_res.json()["status"] == "admitted"

    # 7. Bob polls join-status after admission -> receives LiveKit WebRTC Token!
    bob_status_2 = client.get(f"/api/meetings/{code}/join-status?identity=guest-bob-2").json()
    assert bob_status_2["admission_status"] == "ADMITTED"
    assert bob_status_2["token"] is not None
    assert len(bob_status_2["token"]) > 20

    # 8. Host mutes all
    mute_res = client.post(f"/api/meetings/{code}/mute-all")
    assert mute_res.status_code == 200
    assert mute_res.json()["status"] == "muted_all"

    # 9. Host toggles lock
    sec_res = client.patch(f"/api/meetings/{code}/security", json={"is_locked": True})
    assert sec_res.status_code == 200
    assert sec_res.json()["is_locked"] is True

    # 10. Another participant Charlie tries to join locked meeting
    charlie_res = client.post(
        f"/api/meetings/{code}/join",
        json={"display_name": "Charlie", "is_host": False, "identity": "charlie-3"},
    )
    assert charlie_res.status_code == 403
    assert "locked" in charlie_res.json()["detail"].lower()
