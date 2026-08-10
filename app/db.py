import os
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
from app.paths import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, index=True)
    password_hash = Column(String(200))
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
    is_fresher = Column(Integer, default=0)  # 1 = fresher/entry-level
    hr_email = Column(String(300), default="")  # extracted HR contact email
    gmail_link = Column(Text, default="")
    cv_path = Column(String(300), default="")
    status = Column(String(20), default="new")
    posted_date = Column(DateTime)
    deadline = Column(DateTime)
    created_at = Column(DateTime)

    __table_args__ = (
        __import__("sqlalchemy").UniqueConstraint(
            "source_site", "posting_url", name="uq_job_source_url"
        ),
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


def init_db():
    Base.metadata.create_all(engine)
    # Lightweight migration for older DBs missing newer columns
    with engine.connect() as conn:
        cols_jobs = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(jobs)")]
        if "status" not in cols_jobs:
            conn.exec_driver_sql("ALTER TABLE jobs ADD COLUMN status VARCHAR(20) DEFAULT 'new'")
        if "posted_date" not in cols_jobs:
            conn.exec_driver_sql("ALTER TABLE jobs ADD COLUMN posted_date DATETIME")
        if "deadline" not in cols_jobs:
            conn.exec_driver_sql("ALTER TABLE jobs ADD COLUMN deadline DATETIME")
        if "is_fresher" not in cols_jobs:
            conn.exec_driver_sql("ALTER TABLE jobs ADD COLUMN is_fresher INTEGER DEFAULT 0")
        if "hr_email" not in cols_jobs:
            conn.exec_driver_sql("ALTER TABLE jobs ADD COLUMN hr_email VARCHAR(300) DEFAULT ''")

        cols_uj = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(user_jobs)")]
        if "follow_up_at" not in cols_uj:
            conn.exec_driver_sql("ALTER TABLE user_jobs ADD COLUMN follow_up_at DATETIME")

        cols_profile = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(profile)")]
        if "user_id" not in cols_profile:
            conn.exec_driver_sql("ALTER TABLE profile ADD COLUMN user_id INTEGER REFERENCES users(id)")

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
