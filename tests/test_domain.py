"""Unit tests for the pure evaluation logic."""

from __future__ import annotations

import pytest

from featureflags.domain import (
    BUCKET_COUNT,
    FlagRule,
    FlagType,
    Reason,
    compute_bucket,
    evaluate,
)

USER_COUNT = 10_000


def _users(n: int) -> list[str]:
    return [f"user-{i}" for i in range(n)]


def _percentage_rule(pct: int, key: str = "new-checkout") -> FlagRule:
    return FlagRule(flag_key=key, enabled=True, flag_type=FlagType.PERCENTAGE, percentage=pct)


def test_bucket_is_in_range_and_deterministic() -> None:
    for user in _users(500):
        b1 = compute_bucket("flag-a", user)
        b2 = compute_bucket("flag-a", user)
        assert 0 <= b1 < BUCKET_COUNT
        assert b1 == b2  # stable across calls


def test_bucket_depends_on_flag_key() -> None:
    # Same user, different flags should not be perfectly correlated.
    differing = sum(compute_bucket("flag-a", u) != compute_bucket("flag-b", u) for u in _users(500))
    assert differing > 400  # overwhelmingly independent


def test_percentage_zero_disables_everyone() -> None:
    rule = _percentage_rule(0)
    assert all(not evaluate(rule, u).enabled for u in _users(1000))


def test_percentage_hundred_enables_everyone() -> None:
    rule = _percentage_rule(100)
    assert all(evaluate(rule, u).enabled for u in _users(1000))


def test_percentage_distribution_is_approximately_uniform() -> None:
    """10k users at 30% should land between ~28% and ~32% enabled."""
    rule = _percentage_rule(30)
    enabled = sum(evaluate(rule, u).enabled for u in _users(USER_COUNT))
    share = enabled / USER_COUNT
    assert 0.28 <= share <= 0.32, f"got {share:.3%} enabled"


def test_percentage_rollout_is_monotonic() -> None:
    """A user enabled at a given percentage stays enabled as it grows."""
    users = _users(USER_COUNT)
    prev_enabled: set[str] = set()
    for pct in (5, 10, 20, 30, 50, 75, 100):
        rule = _percentage_rule(pct)
        enabled = {u for u in users if evaluate(rule, u).enabled}
        assert prev_enabled <= enabled, f"lost users going up to {pct}%"
        prev_enabled = enabled


def test_specific_in_bucket_user_stays_enabled() -> None:
    """Find a user in-bucket at 20% and confirm they persist at 30/50/100%."""
    users = _users(USER_COUNT)
    in_at_20 = next(u for u in users if evaluate(_percentage_rule(20), u).enabled)
    for pct in (20, 30, 50, 100):
        assert evaluate(_percentage_rule(pct), in_at_20).enabled


def test_allowlist_overrides_percentage() -> None:
    # A user bucketed out at 0% is still enabled if allowlisted.
    rule = FlagRule(
        flag_key="new-checkout",
        enabled=True,
        flag_type=FlagType.PERCENTAGE,
        percentage=0,
        allowlist=("vip",),
    )
    result = evaluate(rule, "vip")
    assert result.enabled
    assert result.reason is Reason.ALLOWLIST_MATCH


def test_disabled_flag_is_always_off() -> None:
    rule = FlagRule(
        flag_key="new-checkout",
        enabled=False,
        flag_type=FlagType.PERCENTAGE,
        percentage=100,
        allowlist=("vip",),
    )
    for user in ("vip", "someone-else"):
        result = evaluate(rule, user)
        assert not result.enabled
        assert result.reason is Reason.FLAG_DISABLED


def test_boolean_flag_enabled_for_all() -> None:
    rule = FlagRule(flag_key="dark-mode", enabled=True, flag_type=FlagType.BOOLEAN)
    result = evaluate(rule, "anyone")
    assert result.enabled
    assert result.reason is Reason.BOOLEAN_ENABLED


def test_allowlist_type_excludes_non_members() -> None:
    rule = FlagRule(
        flag_key="beta",
        enabled=True,
        flag_type=FlagType.ALLOWLIST,
        allowlist=("alice", "bob"),
    )
    assert evaluate(rule, "alice").enabled
    outsider = evaluate(rule, "carol")
    assert not outsider.enabled
    assert outsider.reason is Reason.NOT_IN_ALLOWLIST


@pytest.mark.parametrize("pct", [10, 25, 40, 60, 90])
def test_reported_bucket_matches_decision(pct: int) -> None:
    rule = _percentage_rule(pct)
    for user in _users(200):
        result = evaluate(rule, user)
        assert result.bucket is not None
        assert result.enabled == (result.bucket < pct)
