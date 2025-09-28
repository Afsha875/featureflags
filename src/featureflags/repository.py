"""Data-access layer. All queries are explicitly scoped to a project so that
tenant isolation is enforced in one place rather than per-endpoint.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Flag, Project
from .domain import FlagRule, FlagType


def create_project(session: Session, *, name: str) -> Project:
    project = Project(name=name)
    session.add(project)
    session.flush()
    return project


def get_project_by_api_key(session: Session, api_key: str) -> Project | None:
    return session.scalar(select(Project).where(Project.api_key == api_key))


def list_flags(session: Session, *, project_id: int) -> list[Flag]:
    stmt = select(Flag).where(Flag.project_id == project_id).order_by(Flag.key)
    return list(session.scalars(stmt))


def get_flag(session: Session, *, project_id: int, key: str) -> Flag | None:
    stmt = select(Flag).where(Flag.project_id == project_id, Flag.key == key)
    return session.scalar(stmt)


def create_flag(
    session: Session,
    *,
    project_id: int,
    key: str,
    flag_type: FlagType,
    enabled: bool,
    percentage: int,
    allowlist: list[str],
) -> Flag:
    flag = Flag(
        project_id=project_id,
        key=key,
        flag_type=flag_type,
        enabled=enabled,
        percentage=percentage,
        allowlist=list(allowlist),
    )
    session.add(flag)
    session.flush()
    return flag


def update_flag(
    session: Session,
    flag: Flag,
    *,
    enabled: bool | None = None,
    flag_type: FlagType | None = None,
    percentage: int | None = None,
    allowlist: list[str] | None = None,
) -> Flag:
    if enabled is not None:
        flag.enabled = enabled
    if flag_type is not None:
        flag.flag_type = flag_type
    if percentage is not None:
        flag.percentage = percentage
    if allowlist is not None:
        flag.allowlist = list(allowlist)
    session.flush()
    return flag


def delete_flag(session: Session, flag: Flag) -> None:
    session.delete(flag)
    session.flush()


def to_rule(flag: Flag) -> FlagRule:
    """Convert an ORM ``Flag`` into an immutable, framework-free rule."""
    return FlagRule(
        flag_key=flag.key,
        enabled=flag.enabled,
        flag_type=FlagType(flag.flag_type),
        percentage=flag.percentage,
        allowlist=tuple(flag.allowlist),
    )
