# GitHub repository resolution

The first GitHub ingestion step resolves every exact curated `owner/name` entry
in `db/seed/technology_universe.yml` to its immutable GitHub repository ID.
The current universe has 45 technologies and 144 distinct repositories.

## Prerequisites

Set `DATABASE_URL_DIRECT` (or `DATABASE_URL`) and `GITHUB_TOKEN`. The token
needs public repository read access. It is read only from environment settings
and is never logged. Apply the migration and seed technology rows first:

```powershell
uv run alembic upgrade head
uv run python -m workers.seed.load_universe
```

## Run

```powershell
uv run python -m workers.github.resolve
```

The worker calls GitHub's exact `GET /repos/{owner}/{repo}` endpoint, follows
transfers, uses bounded retry/backoff for transport and 5xx failures, and stops
when GitHub reports that the rate limit is exhausted.

It writes `repository` rows keyed by immutable GitHub IDs plus the supported
metadata (name, owner, description, homepage, language, topics, licence,
default branch, archive/fork state, timestamps and current counters). It also
creates or refreshes `technology_repository` links using the curated relation
and weight. The current schema has no visibility field, so visibility is not
stored.

Repeated runs update mutable metadata in place and do not duplicate repository
or relationship rows. If one or more repositories fail, successful resolutions
are still committed and the `ingestion_run` is recorded as failed with the
individual failures in its cursor; the command exits non-zero.
