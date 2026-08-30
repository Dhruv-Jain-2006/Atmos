"""Audit the NULL-stars defect."""
from internetweather.config import get_settings
from sqlalchemy import create_engine, func, select, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from internetweather.models import RepositoryMetricDaily, Repository
from datetime import date

url = get_settings().worker_database_url
engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 10})
s = sessionmaker(bind=engine)()

today = date(2026, 8, 29)
yesterday = date(2026, 8, 28)

null_stars_repo_ids = s.execute(
    select(RepositoryMetricDaily.repository_id)
    .where(RepositoryMetricDaily.day == today)
    .where(RepositoryMetricDaily.stars.is_(None))
    .where(RepositoryMetricDaily.is_backfilled == False)
).scalars().all()

has_stars_repo_ids = s.execute(
    select(RepositoryMetricDaily.repository_id)
    .where(RepositoryMetricDaily.day == today)
    .where(RepositoryMetricDaily.stars.isnot(None))
    .where(RepositoryMetricDaily.is_backfilled == False)
).scalars().all()

print(f"Repos with NULL stars today: {len(null_stars_repo_ids)}")
print(f"Repos WITH stars today: {len(has_stars_repo_ids)}")

print("\n--- NULL stars: yesterday row ---")
for rid in null_stars_repo_ids[:5]:
    row = s.execute(
        select(RepositoryMetricDaily)
        .where(RepositoryMetricDaily.repository_id == rid)
        .where(RepositoryMetricDaily.day == yesterday)
    ).scalar_one_or_none()
    repo = s.get(Repository, rid)
    if row:
        print(f"  {repo.full_name}: yest.stars={row.stars} backfilled={row.is_backfilled} | repo.stars={repo.stars}")
    else:
        print(f"  {repo.full_name}: NO yesterday row | repo.stars={repo.stars}")

print("\n--- Has stars: yesterday row ---")
for rid in has_stars_repo_ids[:5]:
    row = s.execute(
        select(RepositoryMetricDaily)
        .where(RepositoryMetricDaily.repository_id == rid)
        .where(RepositoryMetricDaily.day == yesterday)
    ).scalar_one_or_none()
    repo = s.get(Repository, rid)
    if row:
        print(f"  {repo.full_name}: yest.stars={row.stars} backfilled={row.is_backfilled} | repo.stars={repo.stars}")
    else:
        print(f"  {repo.full_name}: NO yesterday row | repo.stars={repo.stars}")

# Check: for NULL-stars repos, is stars_delta also NULL?
print("\n--- NULL stars: delta check ---")
for rid in null_stars_repo_ids[:3]:
    row = s.execute(
        select(RepositoryMetricDaily)
        .where(RepositoryMetricDaily.repository_id == rid)
        .where(RepositoryMetricDaily.day == today)
    ).scalar_one()
    print(f"  repo_id={rid}: stars={row.stars} stars_delta={row.stars_delta} forks={row.forks} forks_delta={row.forks_delta}")

# Check: what does the TODAY row look like for NULL-stars repos?
print("\n--- NULL stars: today row full ---")
for rid in null_stars_repo_ids[:3]:
    row = s.execute(
        select(RepositoryMetricDaily)
        .where(RepositoryMetricDaily.repository_id == rid)
        .where(RepositoryMetricDaily.day == today)
    ).scalar_one()
    repo = s.get(Repository, rid)
    print(f"  {repo.full_name}: stars={row.stars} forks={row.forks} watchers={row.watchers} open_issues={row.open_issues} commits={row.commits} releases={row.releases} contributors={row.contributors_active} backfilled={row.is_backfilled}")

# The KEY question: does the repo table have the correct stars?
print("\n--- Repo table stars for NULL-stars repos ---")
for rid in null_stars_repo_ids[:5]:
    repo = s.get(Repository, rid)
    print(f"  {repo.full_name}: repo.stars={repo.stars} repo.forks={repo.forks} repo.watchers={repo.watchers} repo.open_issues={repo.open_issues}")

engine.dispose()
