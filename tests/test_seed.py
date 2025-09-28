"""The seed script must produce real, in-range figures."""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from featureflags.seed import ROLLOUT_PERCENTAGE, USER_COUNT, seed


def test_seed_produces_in_range_rollout(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        enabled, total = seed(session)
    assert total == USER_COUNT
    share = enabled / total
    lower = (ROLLOUT_PERCENTAGE - 2) / 100
    upper = (ROLLOUT_PERCENTAGE + 2) / 100
    assert lower <= share <= upper, f"got {share:.3%}"
