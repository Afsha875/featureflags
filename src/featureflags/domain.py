"""Pure feature-flag evaluation logic.

This module has no framework or database dependencies so the evaluation
rules can be unit-tested in isolation and reasoned about on their own.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum

# Buckets are 0..(BUCKET_COUNT - 1). Using 100 buckets means a flag
# ``percentage`` maps one-to-one onto the number of buckets that are "in".
BUCKET_COUNT = 100


class FlagType(str, Enum):
    """The evaluation strategy a flag uses."""

    BOOLEAN = "boolean"
    PERCENTAGE = "percentage"
    ALLOWLIST = "allowlist"


class Reason(str, Enum):
    """Machine-readable explanation for an evaluation outcome."""

    FLAG_NOT_FOUND = "flag_not_found"
    FLAG_DISABLED = "flag_disabled"
    ALLOWLIST_MATCH = "allowlist_match"
    NOT_IN_ALLOWLIST = "not_in_allowlist"
    BOOLEAN_ENABLED = "boolean_enabled"
    PERCENTAGE_IN_ROLLOUT = "percentage_in_rollout"
    PERCENTAGE_OUT_OF_ROLLOUT = "percentage_out_of_rollout"


@dataclass(frozen=True, slots=True)
class FlagRule:
    """A framework-agnostic snapshot of a flag's evaluable state."""

    flag_key: str
    enabled: bool
    flag_type: FlagType
    percentage: int = 0
    allowlist: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Evaluation:
    """The result of evaluating a flag for a single user."""

    enabled: bool
    reason: Reason
    # Present only for percentage rollouts; useful for debugging/telemetry.
    bucket: int | None = None


def compute_bucket(flag_key: str, user_id: str) -> int:
    """Deterministically map ``(flag_key, user_id)`` to a bucket in ``[0, 100)``.

    The mapping is stable across processes and machines because it relies on
    SHA-256 rather than Python's salted ``hash``. Folding the flag key into the
    digest means a given user lands in a different bucket per flag, so rollouts
    of different flags are independent of one another.
    """
    digest = hashlib.sha256(f"{flag_key}:{user_id}".encode()).digest()
    # 8 bytes is far more entropy than we need for 100 buckets and keeps the
    # modulo bias negligible.
    value = int.from_bytes(digest[:8], "big")
    return value % BUCKET_COUNT


def evaluate(rule: FlagRule, user_id: str) -> Evaluation:
    """Evaluate ``rule`` for ``user_id``.

    Precedence (highest first):

    1. A disabled flag is always off.
    2. An allowlist match is always on -- it overrides percentage rollout.
    3. Otherwise the flag's own type decides.
    """
    if not rule.enabled:
        return Evaluation(enabled=False, reason=Reason.FLAG_DISABLED)

    # Allowlist wins over percentage: an explicitly listed user is always in,
    # regardless of where the hash would have bucketed them.
    if user_id in rule.allowlist:
        return Evaluation(enabled=True, reason=Reason.ALLOWLIST_MATCH)

    if rule.flag_type is FlagType.BOOLEAN:
        return Evaluation(enabled=True, reason=Reason.BOOLEAN_ENABLED)

    if rule.flag_type is FlagType.ALLOWLIST:
        return Evaluation(enabled=False, reason=Reason.NOT_IN_ALLOWLIST)

    # Percentage rollout.
    bucket = compute_bucket(rule.flag_key, user_id)
    if bucket < rule.percentage:
        return Evaluation(enabled=True, reason=Reason.PERCENTAGE_IN_ROLLOUT, bucket=bucket)
    return Evaluation(enabled=False, reason=Reason.PERCENTAGE_OUT_OF_ROLLOUT, bucket=bucket)
