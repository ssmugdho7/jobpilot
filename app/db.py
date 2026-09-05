import os
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime, ForeignKey, inspect, UniqueConstraint
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.types import JSON
from datetime import datetime
from app.paths import DATABASE_URL, IS_POSTGRES

_connect_args = {} if IS_POSTGRES else {"check_same_thread": False}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, index=True)
    password_hash = Column(String(200))
    onboarding_done = Column(Integer, default=0)  # 1 = onboarding completed
    pref_roles = Column(Text, default="")  # comma-separated preferred roles
    pref_days = Column(Integer, default=30)  # preferred days filter
    created_at = Column(DateTime, default=datetime.utcnow)


class UserJob(Base):
    __tablename__ = "user_jobs"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), primary_key=True)
    status = Column(String(20), default="new")
    cv_path = Column(String(300), default="")
    follow_up_at = Column(DateTime)  # set when status=applied, reminder after 5 days
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    title = Column(String(300))
    company = Column(String(300), default="")
    location = Column(String(200), default="")
    source_site = Column(String(200), default="")
    posting_url = Column(Text, default="")
    snippet = Column(Text, default="")
    role = Column(String(100), default="")
    relevance_score = Column(Float, default=0.0)
    experience_level = Column(String(20), default="")  # fresher / 2y / 3y / 3y_plus
    hr_email = Column(String(300), default="")  # extracted HR contact email
    gmail_link = Column(Text, default="")
    cv_path = Column(String(300), default="")
    status = Column(String(20), default="new")
    posted_date = Column(DateTime)
    deadline = Column(DateTime)
    created_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint("source_site", "posting_url", name="uq_job_source_url"),
    )


class Profile(Base):
    __tablename__ = "profile"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=True)
    name = Column(String(200), default="")
    email = Column(String(200), default="")
    phone = Column(String(100), default="")
    linkedin = Column(String(300), default="")
    github = Column(String(300), default="")
    portfolio = Column(String(300), default="")
    summary = Column(Text, default="")
    education = Column(Text, default="")
    experience = Column(Text, default="")
    skills = Column(Text, default="")  # comma-separated
    cv_file = Column(String(300), default="")  # stored filename under data/uploads


class UserCV(Base):
    __tablename__ = "user_cvs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    file_path = Column(String(500), nullable=False)
    parsed_profile = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String(100), primary_key=True)
    value = Column(String(500), default="")


def init_db():
    Base.metadata.create_all(engine)

    if IS_POSTGRES:
        _migrate_pg()
    else:
        _migrate_sqlite()

    # Ensure CV upload directory exists
    from app.paths import CV_UPLOAD_DIR
    os.makedirs(CV_UPLOAD_DIR, exist_ok=True)


def _col_names(table: str) -> list[str]:
    return [col["name"] for col in inspect(engine).get_columns(table)]


def _add_col_sqlite(table: str, col: str, typedef: str):
    cols = _col_names(table)
    if col not in cols:
        with engine.connect() as conn:
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
            conn.commit()


def _migrate_sqlite():
    for table, col, typedef in [
        ("jobs", "status", "VARCHAR(20) DEFAULT 'new'"),
        ("jobs", "posted_date", "DATETIME"),
        ("jobs", "deadline", "DATETIME"),
        ("jobs", "is_fresher", "INTEGER DEFAULT 0"),
        ("jobs", "hr_email", "VARCHAR(300) DEFAULT ''"),
        ("jobs", "experience_level", "VARCHAR(20) DEFAULT ''"),
        ("user_jobs", "follow_up_at", "DATETIME"),
        ("users", "onboarding_done", "INTEGER DEFAULT 0"),
        ("users", "pref_roles", "TEXT DEFAULT ''"),
        ("users", "pref_days", "INTEGER DEFAULT 30"),
        ("profile", "user_id", "INTEGER REFERENCES users(id)"),
    ]:
        _add_col_sqlite(table, col, typedef)


def _add_col_pg(conn, table: str, col: str, typedef: str):
    try:
        conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typedef}")
    except Exception:
        pass  # column already exists or other non-fatal issue


def _migrate_pg():
    with engine.connect() as conn:
        for table, col, typedef in [
            ("jobs", "status", "VARCHAR(20) DEFAULT 'new'"),
            ("jobs", "posted_date", "TIMESTAMP"),
            ("jobs", "deadline", "TIMESTAMP"),
            ("jobs", "is_fresher", "INTEGER DEFAULT 0"),
            ("jobs", "hr_email", "VARCHAR(300) DEFAULT ''"),
            ("jobs", "experience_level", "VARCHAR(20) DEFAULT ''"),
            ("user_jobs", "follow_up_at", "TIMESTAMP"),
            ("users", "onboarding_done", "INTEGER DEFAULT 0"),
            ("users", "pref_roles", "TEXT DEFAULT ''"),
            ("users", "pref_days", "INTEGER DEFAULT 30"),
            ("profile", "user_id", "INTEGER REFERENCES users(id)"),
        ]:
            _add_col_pg(conn, table, col, typedef)
        conn.commit()


def get_or_create_profile(user_id: int, session: "Session | None" = None) -> Profile:
    """Return the Profile row for user_id."""
    owns_session = session is None
    if owns_session:
        session = SessionLocal()
    try:
        profile = session.query(Profile).filter_by(user_id=user_id).first()
        if profile is None:
            profile = Profile(user_id=user_id)
            session.add(profile)
            session.commit()
        if owns_session:
            session.expunge(profile)
        return profile
    finally:
        if owns_session:
            session.close()


def get_user_job(user_id: int, job_id: int, session) -> UserJob:
    uj = session.query(UserJob).filter_by(user_id=user_id, job_id=job_id).first()
    if not uj:
        uj = UserJob(user_id=user_id, job_id=job_id, status="new", cv_path="")
        session.add(uj)
        session.flush()
    return uj


def profile_to_dict(profile: Profile) -> dict:
    return {
        "name": profile.name or "",
        "email": profile.email or "",
        "phone": profile.phone or "",
        "linkedin": profile.linkedin or "",
        "github": profile.github or "",
        "portfolio": profile.portfolio or "",
        "summary": profile.summary or "",
        "education": profile.education or "",
        "experience": profile.experience or "",
        "skills": [s.strip() for s in (profile.skills or "").split(",") if s.strip()],
        "cv_file": profile.cv_file or "",
    }


def get_setting(key: str, default: str = "") -> str:
    session = SessionLocal()
    try:
        row = session.query(AppSetting).filter_by(key=key).first()
        return row.value if row else default
    finally:
        session.close()


def set_setting(key: str, value: str):
    session = SessionLocal()
    try:
        row = session.query(AppSetting).filter_by(key=key).first()
        if row:
            row.value = value
        else:
            session.add(AppSetting(key=key, value=value))
        session.commit()
    finally:
        session.close()


def get_user_cvs(user_id: int, session=None) -> list:
    """Return all CVs for a user, ordered by created_at desc."""
    owns_session = session is None
    if owns_session:
        session = SessionLocal()
    try:
        cvs = session.query(UserCV).filter_by(user_id=user_id).order_by(UserCV.created_at.desc()).all()
        if owns_session:
            for cv in cvs:
                session.expunge(cv)
        return cvs
    finally:
        if owns_session:
            session.close()


def get_user_cv(cv_id: int, user_id: int, session=None) -> "UserCV | None":
    """Return a specific CV if it belongs to the user."""
    owns_session = session is None
    if owns_session:
        session = SessionLocal()
    try:
        cv = session.query(UserCV).filter_by(id=cv_id, user_id=user_id).first()
        if owns_session and cv:
            session.expunge(cv)
        return cv
    finally:
        if owns_session:
            session.close()


def user_cv_to_dict(cv) -> dict:
    """Convert a UserCV ORM object to a dict."""
    return {
        "id": cv.id,
        "name": cv.name or "",
        "file_path": cv.file_path or "",
        "parsed_profile": cv.parsed_profile or {},
        "created_at": cv.created_at.isoformat() if cv.created_at else "",
    }


def is_fb_post_search_enabled() -> bool:
    """Check if FB post search is enabled. DB > env > yaml."""
    # 1. Check DB setting
    db_val = get_setting("fb_post_search_enabled")
    if db_val:
        return db_val.lower() in ("true", "1", "yes", "on")
    # 2. Check env var
    env_val = os.getenv("FB_POST_SEARCH_ENABLED")
    if env_val is not None:
        return env_val.strip().lower() in ("true", "1", "yes", "on")
    # 3. Check yaml config
    try:
        from app.config import load_fb_post_search_config
        cfg = load_fb_post_search_config()
        return bool(cfg.get("enabled", True))
    except Exception:
        return False
