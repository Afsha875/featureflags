"""Seed/demo script.

Creates two projects with a spread of flag types, then evaluates a large
synthetic user population to show that the percentage rollout is both
deterministic and approximately uniform. Every number printed here is
computed live -- nothing is hard-coded.

Run with::

    uv run featureflags-seed
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from .db import create_engine_and_sessionmaker, init_db
from .domain import FlagRule, FlagType, evaluate
from .repository import create_flag, create_project, get_flag, list_flags, to_rule

USER_COUNT = 10_000
ROLLOUT_KEY = "new-checkout"
ROLLOUT_PERCENTAGE = 30


def _synthetic_users(n: int) -> list[str]:
    return [f"user-{i}" for i in range(n)]


def _count_enabled(session: Session, project_id: int, flag_key: str, users: list[str]) -> int:
    flag = get_flag(session, project_id=project_id, key=flag_key)
    assert flag is not None
    rule = to_rule(flag)
    return sum(1 for u in users if evaluate(rule, u).enabled)


def seed(session: Session) -> tuple[int, int]:
    """Populate the database and return ``(enabled_count, user_count)`` for the
    headline 30% rollout so callers (README, tests) can quote real figures.
    """
    acme = create_project(session, name="Acme")
    globex = create_project(session, name="Globex")

    # Acme: a percentage rollout plus an allowlist override on the same flag.
    create_flag(
        session,
        project_id=acme.id,
        key=ROLLOUT_KEY,
        flag_type=FlagType.PERCENTAGE,
        enabled=True,
        percentage=ROLLOUT_PERCENTAGE,
        allowlist=["vip-user"],
    )
    create_flag(
        session,
        project_id=acme.id,
        key="dark-mode",
        flag_type=FlagType.BOOLEAN,
        enabled=True,
        percentage=0,
        allowlist=[],
    )
    create_flag(
        session,
        project_id=acme.id,
        key="beta-dashboard",
        flag_type=FlagType.ALLOWLIST,
        enabled=True,
        percentage=0,
        allowlist=["user-1", "user-2", "user-3"],
    )

    # Globex: same flag key, different rules -- proves keys are per-tenant.
    create_flag(
        session,
        project_id=globex.id,
        key=ROLLOUT_KEY,
        flag_type=FlagType.PERCENTAGE,
        enabled=False,  # disabled: always off for everyone
        percentage=100,
        allowlist=[],
    )
    session.commit()

    users = _synthetic_users(USER_COUNT)
    enabled = _count_enabled(session, acme.id, ROLLOUT_KEY, users)
    return enabled, len(users)


def _print_report(session: Session) -> tuple[int, int]:
    users = _synthetic_users(USER_COUNT)
    enabled, total = seed(session)
    pct = 100.0 * enabled / total

    acme_flags = list_flags(session, project_id=1)

    print("=" * 60)
    print("featureflags demo")
    print("=" * 60)
    print("\nProject 'Acme' flags:")
    for flag in acme_flags:
        print(
            f"  - {flag.key:<16} type={flag.flag_type:<11} "
            f"enabled={flag.enabled} pct={flag.percentage} "
            f"allowlist={flag.allowlist}"
        )

    print(f"\nPercentage rollout '{ROLLOUT_KEY}' @ {ROLLOUT_PERCENTAGE}%:")
    print(f"  of {total} users, {enabled} enabled ({pct:.1f}%)")

    # Monotonicity: a user enabled at a lower percentage stays enabled higher.
    rollout = get_flag(session, project_id=1, key=ROLLOUT_KEY)
    assert rollout is not None
    print("\n  enabled count grows monotonically with the rollout percentage:")
    print("  pct  enabled   share")
    prev_enabled_set: set[str] = set()
    monotonic = True
    for pct_step in (10, 20, 30, 50, 100):
        rule = FlagRule(
            flag_key=rollout.key,
            enabled=True,
            flag_type=FlagType.PERCENTAGE,
            percentage=pct_step,
        )
        enabled_set = {u for u in users if evaluate(rule, u).enabled}
        if not prev_enabled_set.issubset(enabled_set):
            monotonic = False
        prev_enabled_set = enabled_set
        share = 100.0 * len(enabled_set) / total
        print(f"  {pct_step:>3}  {len(enabled_set):>7}   {share:>5.1f}%")
    print(f"\n  monotonic across all steps: {monotonic}")

    # Allowlist override: 'vip-user' is on even though the hash would bucket
    # them out of a 30% rollout.
    vip = evaluate(to_rule(rollout), "vip-user")
    print(f"\n  allowlist override: 'vip-user' -> enabled={vip.enabled} reason={vip.reason.value}")
    return enabled, total


def main() -> None:
    engine, factory = create_engine_and_sessionmaker("sqlite:///:memory:")
    init_db(engine)
    session_maker: sessionmaker[Session] = factory
    with session_maker() as session:
        _print_report(session)


if __name__ == "__main__":
    main()
