# featureflags

A small but real multi-tenant feature-flag evaluation service. Each project (tenant, identified by an API key) defines flags; an SDK or backend asks the service "is new-checkout on for this user?" and gets a deterministic, explainable answer.

Three flag strategies are supported:

- boolean - a simple on/off switch.
- percentage - a gradual rollout. A user is bucketed by a stable hash of user_id + flag_key, so the same user always gets the same answer, and the set of enabled users only ever grows as you raise the percentage.
- allowlist - an explicit set of user ids. An allowlist match overrides percentage rollout, which is how you dogfood a flag with your own team before it reaches 1% of traffic.

## Why it matters

Rolling out a risky change to 5% of users only works if "5%" is stable and uniform: the same users stay in the cohort as you ramp, and 5% really means ~5% of traffic, not 0% or 12%. This service gets that right with a hash-based bucketing scheme (SHA-256, 100 buckets) and proves it with tests. It is also multi-tenant: two projects can each own a flag named new-checkout with completely independent rules, and neither can read or evaluate the other's flags.

## Quickstart

Requires uv and Python 3.12.

```bash
uv sync

# Run the demo: seeds two projects + flags and evaluates 10k synthetic users.
uv run featureflags-seed

# Or run the HTTP service.
uv run uvicorn featureflags.app:app --reload
# Interactive docs at http://127.0.0.1:8000/docs
```

### Talking to the API

```bash
# 1. Create a project -> returns an API key.
curl -s localhost:8000/projects -d '{"name":"Acme"}' -H 'content-type: application/json'
# {"id":1,"name":"Acme","api_key":"ff_..."}

KEY=ff_...   # paste the key from above

# 2. Define a 30% rollout with a team allowlist override.
curl -s localhost:8000/admin/flags -H "X-API-Key: $KEY" -H 'content-type: application/json' \
  -d '{"key":"new-checkout","flag_type":"percentage","percentage":30,"allowlist":["vip-user"]}'

# 3. Evaluate for one user.
curl -s localhost:8000/evaluate -H "X-API-Key: $KEY" -H 'content-type: application/json' \
  -d '{"flag_key":"new-checkout","user_id":"user-42"}'
# {"flag_key":"new-checkout","enabled":false,"reason":"percentage_out_of_rollout","bucket":62}

# 4. Bootstrap an SDK: all flags for a user in one call.
curl -s localhost:8000/evaluate/batch -H "X-API-Key: $KEY" -H 'content-type: application/json' \
  -d '{"user_id":"user-42"}'
```

Every evaluation returns a reason, so a decision is never a black box: flag_not_found, flag_disabled, allowlist_match, not_in_allowlist, boolean_enabled, percentage_in_rollout, percentage_out_of_rollout.

## Example output (real, from the seed script)

This is the verbatim output of uv run featureflags-seed - every number is computed live over 10,000 synthetic users, not hand-written:

```
Percentage rollout 'new-checkout' @ 30%:
  of 10000 users, 2989 enabled (29.9%)

  enabled count grows monotonically with the rollout percentage:
  pct  enabled   share
   10     1009    10.1%
   20     1996    20.0%
   30     2989    29.9%
   50     4950    49.5%
  100    10000   100.0%

  monotonic across all steps: True

  allowlist override: 'vip-user' -> enabled=True reason=allowlist_match
```

So at a 30% rollout, 2,989 of 10,000 users (29.9%) are enabled - within the expected uniform band - and the cohort only grows as the percentage rises (monotonic), which is exactly the property you want when ramping a release.

## How to test

```bash
uv run ruff check .          # lint
uv run ruff format --check . # formatting
uv run mypy .                # strict type-checking
uv run pytest -q             # 30 tests
```

The suite (tests/) covers real behavior, not trivial asserts:

- Determinism - the same user/flag always buckets identically.
- Uniformity - 10k users at 30% land in the 28-32% band.
- Monotonicity - a user enabled at 20% stays enabled at 30/50/100%.
- Precedence - allowlist overrides percentage; a disabled flag is always off; an unknown flag returns false with flag_not_found.
- Tenant isolation - project B gets a 404 for project A's flags and cannot read, evaluate, modify, or delete them; two tenants' identically-named flags evaluate independently.

## Architecture

```
src/featureflags/
  domain.py      Pure evaluation logic: hashing, bucketing, precedence rules.
                 No framework/DB imports -> trivially unit-testable.
  db.py          SQLAlchemy 2.0 ORM models (Project, Flag) + engine/session.
  repository.py  All queries, every one scoped by project_id (isolation in one place).
  schemas.py     Pydantic request/response models + validation.
  app.py         FastAPI wiring: X-API-Key auth, admin API, evaluation API.
  seed.py        Runnable demo that produces the real figures above.
```

The layering is deliberate: the decision (domain.evaluate) is a pure function over an immutable FlagRule, decoupled from HTTP and storage. The repository is the only layer that touches the database, and it always filters by project_id, so tenant isolation is enforced structurally rather than remembered at each endpoint. Storage is SQLite via SQLAlchemy (sync); the app factory takes a session factory, so tests run against a shared in-memory database with zero mocking.

## Deployment

A Dockerfile builds a slim image that serves the app with uvicorn:

```bash
docker build -t featureflags .
docker run -p 8000:8000 featureflags
```

## Maintainer

This project is maintained by Afsha Fathima, a Python Backend Developer specializing in building robust REST APIs and scalable backend services. With a focus on reliability and performance, this service implements industry-standard practices for feature flag management and multi-tenant isolation.

Contact Information:
- Email: fathimaafsha08@gmail.com
- LinkedIn: https://www.linkedin.com/in/afsha-fathima-lnu-a29996298/