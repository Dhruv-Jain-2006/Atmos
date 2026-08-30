"""Shared vocabulary for the whole system.

Everything that both the database and the API surface need to agree on lives
here, so the frontend never hardcodes a weather state or a subdomain name.
"""

from __future__ import annotations

from enum import StrEnum


class Subdomain(StrEnum):
    """Technology subdomains within the AI-engineering domain."""

    AGENTIC_AI = "agentic_ai"
    LLM_ECOSYSTEM = "llm_ecosystem"
    RAG = "rag"
    AI_INFRA = "ai_infra"
    MULTIMODAL = "multimodal"
    MLOPS = "mlops"
    AI_SECURITY = "ai_security"


class WeatherState(StrEnum):
    """Computed atmospheric state of a technology.

    NEVER assign these by hand. They are the output of
    ``internetweather.analysis.weather_state.classify`` operating on measured
    signals. A technology with insufficient history is STABLE with low
    confidence — not EMERGING.
    """

    HOT = "hot"
    EMERGING = "emerging"
    STABLE = "stable"
    COOLING = "cooling"
    BREAKING = "breaking"
    STORM = "storm"


#: Presentation metadata served with the API so the frontend has one source of
#: truth for the semantic vocabulary.
WEATHER_STATE_META: dict[WeatherState, dict[str, str]] = {
    WeatherState.HOT: {
        "glyph": "🔥",
        "label": "Hot",
        "meaning": "Sustained high growth well above its own baseline.",
    },
    WeatherState.EMERGING: {
        "glyph": "🌱",
        "label": "Emerging",
        "meaning": "Young and accelerating from a small base.",
    },
    WeatherState.STABLE: {
        "glyph": "🌤",
        "label": "Stable",
        "meaning": "Activity consistent with its own recent baseline.",
    },
    WeatherState.COOLING: {
        "glyph": "❄️",
        "label": "Cooling",
        "meaning": "Activity decaying relative to its own baseline.",
    },
    WeatherState.BREAKING: {
        "glyph": "⚡",
        "label": "Breaking",
        "meaning": "A discrete event just moved this technology sharply.",
    },
    WeatherState.STORM: {
        "glyph": "🌪",
        "label": "Storm",
        "meaning": "Violent, unstable activity — direction unresolved.",
    },
}


class RepoRelation(StrEnum):
    """How a repository relates to the technology it sensors."""

    CANONICAL = "canonical"
    IMPLEMENTATION = "implementation"
    INTEGRATION = "integration"
    ECOSYSTEM = "ecosystem"


class RelationshipType(StrEnum):
    """Edges between technologies, used by Explore and the Research page."""

    DEPENDS_ON = "depends_on"
    ALTERNATIVE_TO = "alternative_to"
    COMPLEMENTS = "complements"
    CO_OCCURS = "co_occurs"


class EventType(StrEnum):
    """Discrete ecosystem events."""

    RELEASE = "release"
    STAR_SPIKE = "star_spike"
    ANOMALY = "anomaly"
    NEW_REPOSITORY = "new_repository"
    ARCHIVED = "archived"
    RENAMED = "renamed"


class RecordSource(StrEnum):
    CURATED = "curated"
    DISCOVERED = "discovered"
    INFERRED = "inferred"


class TrackingState(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    DROPPED = "dropped"


class EpistemicStatus(StrEnum):
    """Required label on every generated claim.

    Enforced at the contract level so speculation can never be presented as
    fact. See CLAUDE.md, "LLM Philosophy".
    """

    OBSERVATION = "observation"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"
    UNKNOWN = "unknown"


class ResearchStatus(StrEnum):
    QUEUED = "queued"
    COLLECTING = "collecting"
    ANALYZING = "analyzing"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    FAILED = "failed"


class IngestionStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    QUOTA_EXHAUSTED = "quota_exhausted"
