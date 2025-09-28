"""FastAPI application wiring: admin API, evaluation API, tenant auth."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from . import repository as repo
from .db import (
    Flag,
    Project,
    create_engine_and_sessionmaker,
    init_db,
)
from .domain import Reason, evaluate
from .schemas import (
    BatchEvaluateRequest,
    BatchEvaluateResponse,
    EvaluateRequest,
    EvaluateResponse,
    FlagCreate,
    FlagOut,
    FlagUpdate,
    ProjectCreate,
    ProjectOut,
)


def create_app(session_factory: sessionmaker[Session]) -> FastAPI:
    app = FastAPI(
        title="featureflags",
        version="0.1.0",
        summary="Multi-tenant feature-flag evaluation service.",
    )

    def get_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    SessionDep = Annotated[Session, Depends(get_session)]

    def require_project(
        session: SessionDep,
        x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    ) -> Project:
        if not x_api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-API-Key header.",
            )
        project = repo.get_project_by_api_key(session, x_api_key)
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key.",
            )
        return project

    ProjectDep = Annotated[Project, Depends(require_project)]

    def _load_owned_flag(session: Session, project: Project, key: str) -> Flag:
        flag = repo.get_flag(session, project_id=project.id, key=key)
        if flag is None:
            # A flag that belongs to another tenant is indistinguishable from
            # one that does not exist -- this is deliberate tenant isolation.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Flag '{key}' not found.",
            )
        return flag

    # ------------------------------------------------------------------ #
    # Health
    # ------------------------------------------------------------------ #
    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # ------------------------------------------------------------------ #
    # Project bootstrap
    # ------------------------------------------------------------------ #
    @app.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
    def create_project(body: ProjectCreate, session: SessionDep) -> Project:
        return repo.create_project(session, name=body.name)

    # ------------------------------------------------------------------ #
    # Admin API (project-scoped via X-API-Key)
    # ------------------------------------------------------------------ #
    @app.get("/admin/flags", response_model=list[FlagOut])
    def list_flags(project: ProjectDep, session: SessionDep) -> list[Flag]:
        return repo.list_flags(session, project_id=project.id)

    @app.post(
        "/admin/flags",
        response_model=FlagOut,
        status_code=status.HTTP_201_CREATED,
    )
    def create_flag(body: FlagCreate, project: ProjectDep, session: SessionDep) -> Flag:
        try:
            return repo.create_flag(
                session,
                project_id=project.id,
                key=body.key,
                flag_type=body.flag_type,
                enabled=body.enabled,
                percentage=body.percentage,
                allowlist=body.allowlist,
            )
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Flag '{body.key}' already exists.",
            ) from exc

    @app.get("/admin/flags/{key}", response_model=FlagOut)
    def get_flag(key: str, project: ProjectDep, session: SessionDep) -> Flag:
        return _load_owned_flag(session, project, key)

    @app.patch("/admin/flags/{key}", response_model=FlagOut)
    def update_flag(key: str, body: FlagUpdate, project: ProjectDep, session: SessionDep) -> Flag:
        flag = _load_owned_flag(session, project, key)
        return repo.update_flag(
            session,
            flag,
            enabled=body.enabled,
            flag_type=body.flag_type,
            percentage=body.percentage,
            allowlist=body.allowlist,
        )

    @app.delete("/admin/flags/{key}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_flag(key: str, project: ProjectDep, session: SessionDep) -> Response:
        flag = _load_owned_flag(session, project, key)
        repo.delete_flag(session, flag)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # ------------------------------------------------------------------ #
    # Evaluation API
    # ------------------------------------------------------------------ #
    @app.post("/evaluate", response_model=EvaluateResponse)
    def evaluate_flag(
        body: EvaluateRequest, project: ProjectDep, session: SessionDep
    ) -> EvaluateResponse:
        flag = repo.get_flag(session, project_id=project.id, key=body.flag_key)
        if flag is None:
            return EvaluateResponse(
                flag_key=body.flag_key,
                enabled=False,
                reason=Reason.FLAG_NOT_FOUND,
            )
        result = evaluate(repo.to_rule(flag), body.user_id)
        return EvaluateResponse(
            flag_key=body.flag_key,
            enabled=result.enabled,
            reason=result.reason,
            bucket=result.bucket,
        )

    @app.post("/evaluate/batch", response_model=BatchEvaluateResponse)
    def evaluate_all(
        body: BatchEvaluateRequest, project: ProjectDep, session: SessionDep
    ) -> BatchEvaluateResponse:
        flags = repo.list_flags(session, project_id=project.id)
        results: dict[str, EvaluateResponse] = {}
        for flag in flags:
            result = evaluate(repo.to_rule(flag), body.user_id)
            results[flag.key] = EvaluateResponse(
                flag_key=flag.key,
                enabled=result.enabled,
                reason=result.reason,
                bucket=result.bucket,
            )
        return BatchEvaluateResponse(user_id=body.user_id, flags=results)

    return app


def build_default_app() -> FastAPI:
    """Application entry point backed by an on-disk SQLite database."""
    engine, factory = create_engine_and_sessionmaker()
    init_db(engine)
    return create_app(factory)


app = build_default_app()
