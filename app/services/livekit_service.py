import logging
from datetime import timedelta
from typing import Optional
from livekit import api
from app.config import settings

logger = logging.getLogger(__name__)


class LiveKitService:
    def __init__(self):
        self.api_key = settings.LIVEKIT_API_KEY or "devkey"
        self.api_secret = settings.LIVEKIT_API_SECRET or "secret-must-be-at-least-32-characters-long-for-hmac-sha256"
        self.livekit_url = settings.LIVEKIT_URL or "wss://zoom-clone-demo.livekit.cloud"

    def is_configured(self) -> bool:
        return bool(settings.LIVEKIT_API_KEY and settings.LIVEKIT_API_SECRET and settings.LIVEKIT_URL)

    def create_token(
        self,
        room_name: str,
        identity: str,
        display_name: str,
        is_host: bool = False,
    ) -> str:
        """Generate a secure LiveKit participant access token."""
        token = (
            api.AccessToken(self.api_key, self.api_secret)
            .with_identity(identity)
            .with_name(display_name)
            .with_ttl(timedelta(hours=6))
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                    room_admin=is_host,
                )
            )
        )
        return token.to_jwt()

    @property
    def http_url(self) -> str:
        return self.livekit_url.replace("wss://", "https://").replace("ws://", "http://")

    async def remove_participant(self, room_name: str, identity: str) -> bool:
        """Disconnect a participant from a LiveKit room."""
        if not self.is_configured():
            logger.warning("LiveKit API is not configured; cannot call server-side remove_participant.")
            return False

        try:
            livekit_api = api.LiveKitAPI(
                url=self.http_url,
                api_key=self.api_key,
                api_secret=self.api_secret,
            )
            await livekit_api.room.remove_participant(
                api.RoomParticipantIdentity(room=room_name, identity=identity)
            )
            await livekit_api.aclose()
            return True
        except Exception as e:
            logger.error(f"Error removing participant {identity} from room {room_name}: {e}")
            return False

    async def mute_published_track(self, room_name: str, identity: str, track_sid: str, muted: bool = True) -> bool:
        """Mute a specific track of a participant."""
        if not self.is_configured():
            return False

        try:
            livekit_api = api.LiveKitAPI(
                url=self.http_url,
                api_key=self.api_key,
                api_secret=self.api_secret,
            )
            await livekit_api.room.mute_published_track(
                api.MuteRoomTrackRequest(
                    room=room_name,
                    identity=identity,
                    track_sid=track_sid,
                    muted=muted,
                )
            )
            await livekit_api.aclose()
            return True
        except Exception as e:
            logger.error(f"Error muting track {track_sid}: {e}")
            return False

    async def delete_room(self, room_name: str) -> bool:
        """Terminate a room and disconnect all participants on LiveKit server."""
        if not self.is_configured():
            logger.warning("LiveKit API is not configured; cannot call delete_room.")
            return False

        try:
            livekit_api = api.LiveKitAPI(
                url=self.http_url,
                api_key=self.api_key,
                api_secret=self.api_secret,
            )
            await livekit_api.room.delete_room(
                api.DeleteRoomRequest(room=room_name)
            )
            await livekit_api.aclose()
            return True
        except Exception as e:
            logger.error(f"Error deleting room {room_name}: {e}")
            return False


livekit_service = LiveKitService()
