"""Background workers.

Run from the repository root, e.g.:

    uv run python -m workers.seed.load_universe
    uv run python -m workers.retention.prune --dry-run

Scheduled by GitHub Actions (locked decision #7). Vercel's Hobby cron fires at
most once per day, which is not a scheduler for a system that observes change.
"""
