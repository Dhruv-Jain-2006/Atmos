"""Deterministic explanation of a weather state.

The hover intelligence preview needs a sentence, and the read path must not call
an LLM to produce one. These sentences only restate measured values, which is why
they are labelled OBSERVATION.

One implementation serves both callers: the detection worker (which has a fresh
``Classification``) and the read API (which has a stored
``technology_signal_daily`` row). Two implementations would drift, and the
preview would stop matching the state beside it.

When the research engine lands it will produce INFERENCE and HYPOTHESIS text on
top of this — never instead of it.
"""

from __future__ import annotations

from dataclasses import dataclass

from internetweather.analysis.weather_state import (
    MIN_SAMPLE_DAYS,
    Classification,
    SignalInput,
    growth_ratio,
)
from internetweather.enums import EpistemicStatus, WeatherState

_OPENER: dict[WeatherState, str] = {
    WeatherState.HOT: "Accelerating sharply",
    WeatherState.EMERGING: "Emerging from a small base",
    WeatherState.STABLE: "Holding steady",
    WeatherState.COOLING: "Cooling",
    WeatherState.BREAKING: "Moved by a discrete event",
    WeatherState.STORM: "Moving without a resolvable direction",
}

#: Below this confidence the classifier is extrapolating from thin data, and the
#: UI must be able to render the difference.
UNKNOWN_CONFIDENCE = 0.35


@dataclass(frozen=True, slots=True)
class PreviewInput:
    """Exactly the columns stored on ``technology_signal_daily``.

    Keeping this aligned with the table means the read path needs no
    recomputation and no extra query to render a preview.
    """

    state: WeatherState
    momentum: float
    confidence: float
    sample_days: int = 0
    star_velocity_7d: float | None = None
    star_velocity_28d: float | None = None
    anomaly_z: float | None = None
    repo_count: int = 0
    active_repo_count: int = 0
    recent_event_magnitude: float = 0.0

    @classmethod
    def from_classification(
        cls, classification: Classification, signals: SignalInput
    ) -> PreviewInput:
        return cls(
            state=classification.state,
            momentum=classification.momentum,
            confidence=classification.confidence,
            sample_days=signals.sample_days,
            star_velocity_7d=signals.star_velocity_7d,
            star_velocity_28d=signals.star_velocity_28d,
            anomaly_z=signals.anomaly_z,
            repo_count=signals.repo_count,
            active_repo_count=signals.active_repo_count,
            recent_event_magnitude=signals.recent_event_magnitude,
        )


def _clauses(preview: PreviewInput) -> list[str]:
    """Measured facts, in the order a reader wants them."""
    clauses: list[str] = []

    ratio = growth_ratio(preview.star_velocity_7d, preview.star_velocity_28d)
    if preview.star_velocity_7d is not None or preview.star_velocity_28d is not None:
        clauses.append(f"star velocity is {ratio:.2f}× its 28-day baseline")

    if preview.anomaly_z:
        clauses.append(f"{preview.anomaly_z:+.1f}σ from its own baseline")

    if preview.recent_event_magnitude:
        clauses.append(
            f"a discrete event of magnitude {preview.recent_event_magnitude:.2f} landed"
        )

    if preview.active_repo_count:
        clauses.append(
            f"{preview.active_repo_count} of {preview.repo_count} repositories active"
        )

    return clauses


def describe(preview: PreviewInput) -> str:
    """One sentence describing what changed, and nothing more.

    Deliberately unembellished. Where the data does not support a claim, the
    sentence says so rather than reaching for a narrative.
    """
    opener = _OPENER[preview.state]

    if preview.sample_days < MIN_SAMPLE_DAYS:
        return (
            f"{opener} — only {preview.sample_days} day(s) of observation, "
            f"{MIN_SAMPLE_DAYS} needed before classifying."
        )

    clauses = _clauses(preview)
    if not clauses:
        return f"{opener}."
    if preview.state is WeatherState.STABLE:
        return f"{opener}: {clauses[0]}."
    return f"{opener}: {'; '.join(clauses[:3])}."


def epistemic_status(confidence: float) -> EpistemicStatus:
    """A low-confidence reading is not an observation; it is an open question."""
    if confidence < UNKNOWN_CONFIDENCE:
        return EpistemicStatus.UNKNOWN
    return EpistemicStatus.OBSERVATION
