from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    import app.models  # ensure models are registered
    Base.metadata.create_all(bind=engine)
    
    # Auto-migrate SQLite columns if not present
    from sqlalchemy import text
    with engine.connect() as conn:
        try:
            # Check meetings columns
            meeting_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(meetings)")).fetchall()]
            if "actual_started_at" not in meeting_cols:
                conn.execute(text("ALTER TABLE meetings ADD COLUMN actual_started_at DATETIME"))
            if "actual_ended_at" not in meeting_cols:
                conn.execute(text("ALTER TABLE meetings ADD COLUMN actual_ended_at DATETIME"))
            if "scheduled_start_at" not in meeting_cols:
                conn.execute(text("ALTER TABLE meetings ADD COLUMN scheduled_start_at DATETIME"))
            if "waiting_room_enabled" not in meeting_cols:
                conn.execute(text("ALTER TABLE meetings ADD COLUMN waiting_room_enabled BOOLEAN DEFAULT 0"))
            if "is_locked" not in meeting_cols:
                conn.execute(text("ALTER TABLE meetings ADD COLUMN is_locked BOOLEAN DEFAULT 0"))
            if "mute_new_participants" not in meeting_cols:
                conn.execute(text("ALTER TABLE meetings ADD COLUMN mute_new_participants BOOLEAN DEFAULT 0"))

            # Check participants columns
            part_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(participants)")).fetchall()]
            if "admission_status" not in part_cols:
                conn.execute(text("ALTER TABLE participants ADD COLUMN admission_status VARCHAR(20) DEFAULT 'ADMITTED'"))
            if "waiting_since" not in part_cols:
                conn.execute(text("ALTER TABLE participants ADD COLUMN waiting_since DATETIME"))

            # Sync legacy timestamps if needed
            conn.execute(text("UPDATE meetings SET actual_started_at = started_at WHERE actual_started_at IS NULL AND started_at IS NOT NULL"))
            conn.execute(text("UPDATE meetings SET actual_ended_at = ended_at WHERE actual_ended_at IS NULL AND ended_at IS NOT NULL"))
            conn.execute(text("UPDATE meetings SET scheduled_start_at = scheduled_time WHERE scheduled_start_at IS NULL AND scheduled_time IS NOT NULL"))
            conn.execute(text("UPDATE participants SET admission_status = 'ADMITTED' WHERE admission_status IS NULL"))
            conn.commit()
        except Exception as mig_err:
            print(f"[migration note] {mig_err}")

    try:
        from app.models.meeting import Meeting
        db = SessionLocal()
        try:
            if db.query(Meeting).count() == 0:
                try:
                    from seed import seed_data
                    seed_data()
                except Exception as seed_err:
                    print(f"[seed note] Auto-seed skipped: {seed_err}")
        finally:
            db.close()
    except Exception as e:
        print(f"[init_db note] {e}")
