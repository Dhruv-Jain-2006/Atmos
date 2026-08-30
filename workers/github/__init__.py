"""GitHub ingestion workers.

GitHub is treated as a developer-behaviour sensor, not a dataset to mirror. Four
jobs, in dependency order:

1. ``resolve``       — curated ``owner/name`` → immutable numeric ids (once, then rarely)
2. ``sync_metrics``  — incremental daily levels and activity counts (hourly-ish)
3. ``backfill_stars``— curated historical star curve for headline repositories (once)
4. ``discover``      — find repositories the curated list does not know about (weekly)

All four share one quota: 5,000 requests/hour on a personal access token.
"""
