"""Weather-state classification.

This module is the reason CLAUDE.md can say "weather states must be computed
from actual signals". It is a pure function: measured signals in, a state and a
confidence out. No database, no network, no LLM.

Two properties are load-bearing:

* Every judgement is relative to a technology's OWN baseline. Comparing vLLM's
  raw star velocity to a small project's would rank by fame, not by change.
* Thin history lowers confidence; it never invents a state. A technology with
  four days of observation is STABLE at low confidence, not EMERGING — that
  distinction is the difference between an observatory and a hype machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import log, tanh

from internetweather.enums import WeatherState

# --- Thresholds -------------------------------------------------------------
# Tuned to be defensible rather than clever. Each is named so a change is a
# deliberate product decision that shows up in review.

#: Below this, we do not claim to know the weather.
MIN_SAMPLE_DAYS = 7
#: History at which the confidence term saturates.
CONFIDENT_SAMPLE_DAYS = 28

#: Growth relative to a technology's own 28-day baseline.
HOT_GROWTH_RATIO = 1.5
COOLING_GROWTH_RATIO = 0.65

#: Standard deviations from a technology's own baseline.
HOT_Z = 1.25
COOLING_Z = -1.0
EMERGING_Z = 0.75
STORM_Z = 2.0

#: A technology is only EMERGING from a small base — otherwise it is just HOT.
EMERGING_MAX_STARS = 15_000
EMERGING_MAX_AGE_DAYS = 550

#: Coefficient of variation above which daily movement is incoherent rather
#: than directional. STORM means "something is happening, direction unresolved".
STORM_VOLATILITY = 1.2
#: Volatility at which the consistency term of confidence reaches zero.
VOLATILITY_CEILING = 2.0

#: A discrete event this large in the last few days outranks trend shape.
BREAKING_EVENT_MAGNITUDE = 0.6

#: Prevents division by zero on technologies with no measurable star flow.
EPS = 0.05

# Momentum composite weights. Acceleration dominates: the product is about
# change, not level.
W_ACCELERATION = 1.0
W_ANOMALY = 0.6
W_ACTIVITY = 0.5
Z_SCALE = 4.0


@dataclass(frozen=True, slots=True)
class SignalInput:
    """Measured inputs. Produced by the detection worker, never by hand."""

    #: Weighted stars/day over the trailing 7 and 28 days.
    star_velocity_7d: float | None = None
    star_velocity_28d: float | None = None
    #: Weighted builder activity/day (commits, releases, contributors composite).
    activity_velocity_7d: float | None = None
    activity_velocity_28d: float | None = None
    #: Standard deviations of the 7-day velocity from the technology's baseline.
    anomaly_z: float | None = None
    #: Coefficient of variation of daily star deltas.
    volatility: float | None = None

    stars_total: int | None = None
    sample_days: int = 0
    repo_count: int = 0
    active_repo_count: int = 0
    #: Age of the technology's oldest canonical repository.
    age_days: int | None = None
    #: Largest event magnitude detected in the last 3 days.
    recent_event_magnitude: float = 0.0


@dataclass(frozen=True, slots=True)
class Driver:
    """One named contribution to the verdict, for explanation and audit."""

    key: str
    value: float
    detail: str


@dataclass(frozen=True, slots=True)
class Classification:
    state: WeatherState
    momentum: float
    confidence: float
    drivers: list[Driver] = field(default_factory=list)
    #: Set when the verdict is a default rather than a positive finding.
    reason: str | None = None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def growth_ratio(recent: float | None, baseline: float | None) -> float:
    """Recent velocity over baseline velocity, smoothed.

    1.0 means "moving exactly as it has been". This ratio, not the absolute
    velocity, is what makes a 200-star project and a 200,000-star project
    comparable.
    """
    return (max(recent or 0.0, 0.0) + EPS) / (max(baseline or 0.0, 0.0) + EPS)


def compute_momentum(signals: SignalInput) -> float:
    """Signed -1..1 composite. Positive means accelerating.

    ``tanh`` bounds the output, which also satisfies the database CHECK
    constraint on ``technology_signal_daily.momentum``.
    """
    star_accel = log(growth_ratio(signals.star_velocity_7d, signals.star_velocity_28d))
    activity_accel = log(
        growth_ratio(signals.activity_velocity_7d, signals.activity_velocity_28d)
    )
    z = _clamp(signals.anomaly_z or 0.0, -Z_SCALE, Z_SCALE) / Z_SCALE

    raw = (
        W_ACCELERATION * star_accel
        + W_ANOMALY * z
        + W_ACTIVITY * activity_accel
    )
    return round(tanh(raw), 6)


def compute_confidence(signals: SignalInput) -> float:
    """0..1. How much the data actually supports any verdict at all.

    Three independent things can undermine a reading: too little history, too
    few repositories agreeing, and movement too erratic to have a direction.
    """
    history = min(1.0, signals.sample_days / CONFIDENT_SAMPLE_DAYS)
    breadth = min(1.0, signals.active_repo_count / 3.0)
    consistency = 1.0 - min(1.0, (signals.volatility or 0.0) / VOLATILITY_CEILING)

    score = 0.5 * history + 0.3 * breadth + 0.2 * consistency
    return round(_clamp(score, 0.0, 1.0), 4)


def _drivers(signals: SignalInput, star_ratio: float, momentum: float) -> list[Driver]:
    drivers = [
        Driver(
            "star_acceleration",
            star_ratio,
            f"star velocity is {star_ratio:.2f}× its 28-day baseline",
        ),
        Driver(
            "momentum",
            momentum,
            f"composite momentum {momentum:+.2f}",
        ),
    ]
    if signals.anomaly_z is not None:
        drivers.append(
            Driver(
                "anomaly",
                signals.anomaly_z,
                f"{signals.anomaly_z:+.1f}σ from its own baseline",
            )
        )
    if signals.active_repo_count:
        drivers.append(
            Driver(
                "breadth",
                float(signals.active_repo_count),
                f"{signals.active_repo_count} of {signals.repo_count} repositories active",
            )
        )
    if signals.recent_event_magnitude:
        drivers.append(
            Driver(
                "event",
                signals.recent_event_magnitude,
                f"a discrete event of magnitude {signals.recent_event_magnitude:.2f}",
            )
        )
    return drivers


def _is_emerging_shape(signals: SignalInput) -> bool:
    """Young or small-based. EMERGING is about where it started, not how fast."""
    small_base = signals.stars_total is not None and signals.stars_total < EMERGING_MAX_STARS
    young = signals.age_days is not None and signals.age_days <= EMERGING_MAX_AGE_DAYS
    return small_base or young


def classify(signals: SignalInput) -> Classification:
    """Assign a weather state from measured signals.

    Rules are evaluated in order of how much they override trend shape: a
    discrete event beats a trend, incoherence beats a direction, and everything
    beats a guess made on thin data.
    """
    momentum = compute_momentum(signals)
    confidence = compute_confidence(signals)
    star_ratio = growth_ratio(signals.star_velocity_7d, signals.star_velocity_28d)
    drivers = _drivers(signals, star_ratio, momentum)
    z = signals.anomaly_z or 0.0

    # 1. Not enough observation to claim anything.
    if signals.sample_days < MIN_SAMPLE_DAYS:
        return Classification(
            state=WeatherState.STABLE,
            momentum=momentum,
            confidence=min(confidence, 0.25),
            drivers=drivers,
            reason=(
                f"only {signals.sample_days} day(s) of observation; "
                f"{MIN_SAMPLE_DAYS} required before classifying"
            ),
        )

    # 2. A discrete event just moved it. That is the story, not the trend.
    if signals.recent_event_magnitude >= BREAKING_EVENT_MAGNITUDE:
        return Classification(WeatherState.BREAKING, momentum, confidence, drivers)

    # 3. Moving violently, but not in a resolvable direction.
    if (signals.volatility or 0.0) >= STORM_VOLATILITY and abs(z) >= STORM_Z:
        return Classification(WeatherState.STORM, momentum, confidence, drivers)

    # 4. Sustained growth well above its own baseline.
    if star_ratio >= HOT_GROWTH_RATIO and z >= HOT_Z:
        if _is_emerging_shape(signals):
            return Classification(WeatherState.EMERGING, momentum, confidence, drivers)
        return Classification(WeatherState.HOT, momentum, confidence, drivers)

    # 5. Accelerating from a small or young base.
    if z >= EMERGING_Z and momentum > 0 and _is_emerging_shape(signals):
        return Classification(WeatherState.EMERGING, momentum, confidence, drivers)

    # 6. Decaying against its own baseline.
    if star_ratio <= COOLING_GROWTH_RATIO and z <= COOLING_Z:
        return Classification(WeatherState.COOLING, momentum, confidence, drivers)

    return Classification(
        WeatherState.STABLE,
        momentum,
        confidence,
        drivers,
        reason="activity consistent with its own recent baseline",
    )
