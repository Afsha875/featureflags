"""Database engine, ORM models, and session helpers (SQLAlchemy 2.0, sync)."""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from .domain import FlagType


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


def generate_api_key() -> str:
    """Return a fresh, URL-safe project API key."""
    return f"ff_{secrets.token_urlsafe(24)}"


class Project(Base):
    """A tenant. Every flag and every evaluation is scoped to one project."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    api_key: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True, default=generate_api_key
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    flags: Mapped[list[Flag]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Flag(Base):
    """A feature flag owned by a single project.

    ``key`` is unique *within* a project, not globally -- two tenants may each
    have a flag named ``new-checkout`` with entirely independent rules.
    """

    __tablename__ = "flags"
    __table_args__ = (UniqueConstraint("project_id", "key", name="uq_project_flag_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    flag_type: Mapped[FlagType] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    percentage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    allowlist: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="flags")


def create_engine_and_sessionmaker(
    url: str = "sqlite:///featureflags.db",
) -> tuple[object, sessionmaker[Session]]:
    """Build a configured engine + session factory for ``url``."""
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return engine, factory


def init_db(engine: object) -> None:
    """Create all tables. Safe to call repeatedly."""
    Base.metadata.create_all(bind=engine)  # type: ignore[arg-type]


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Yield a session, committing on success and rolling back on error."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
