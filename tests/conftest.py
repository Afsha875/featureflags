"""Shared pytest fixtures: an isolated in-memory app + API-key helpers."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from featureflags.app import create_app
from featureflags.db import init_db


@pytest.fixture
def session_factory() -> sessionmaker[Session]:
    # A single shared in-memory connection so every request in a test sees the
    # same database (StaticPool keeps the one connection alive).
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    init_db(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app(session_factory)
    with TestClient(app) as test_client:
        yield test_client


def new_project(client: TestClient, name: str = "Acme") -> str:
    """Create a project and return its API key."""
    resp = client.post("/projects", json={"name": name})
    assert resp.status_code == 201, resp.text
    return str(resp.json()["api_key"])


def auth(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}
