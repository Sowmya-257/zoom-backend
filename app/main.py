import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import health_router, meetings_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize database schema
init_db()

app = FastAPI(
    title="Zoom Video Conferencing API",
    description="Backend API for Scaler Zoom Clone Assignment supporting meetings, participants, and LiveKit WebRTC.",
    version="1.0.0",
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for local dev and flexible deployments
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router)
app.include_router(meetings_router)


@app.get("/")
def root():
    return {
        "service": "Zoom Clone API",
        "status": "online",
        "docs": "/docs",
        "health": "/api/health",
        "frontend": settings.FRONTEND_URL,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
