"""ORM models for the first vertical slice.

Eight tables, in pipeline order:

    technology, technology_repository, repository   -- the universe
    repository_metric_daily                        -- ingested facts
    technology_signal_daily, ecosystem_event       -- derived signals
    technology_relationship                        -- graph edges
    ingestion_run                                  -- operational bookkeeping

Research tables (jobs, findings, evidence) are deliberately absent: the research
engine is out of scope for this slice, and an unused table is a migration we would
have to justify later. Their API contracts exist; their storage arrives with them.
"""

from internetweather.models.base import Base, TimestampMixin
from internetweather.models.ingestion import IngestionRun
from internetweather.models.repository import Repository, RepositoryMetricDaily
from internetweather.models.signal import EcosystemEvent, TechnologySignalDaily
from internetweather.models.technology import (
    Technology,
    TechnologyRelationship,
    TechnologyRepository,
)

__all__ = [
    "Base",
    "EcosystemEvent",
    "IngestionRun",
    "Repository",
    "RepositoryMetricDaily",
    "Technology",
    "TechnologyRelationship",
    "TechnologyRepository",
    "TechnologySignalDaily",
    "TimestampMixin",
]
