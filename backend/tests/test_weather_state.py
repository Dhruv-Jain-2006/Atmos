"""The classifier is the product's central claim, so it is tested directly.

No database and no network — these are pure-function tests over synthetic
signals, which is what makes them meaningful before any ingestion exists.
"""

from __future__ import annotations

import pytest

from internetweather.analysis.explanation import (
    PreviewInput,
    describe,
    epistemic_status,
)
from internetweather.analysis.weather_state import (
    MIN_SAMPLE_DAYS,
    SignalInput,
    classify,
    compute_momentum,
    growth_ratio,
)
from internetweather.enums import EpistemicStatus, WeatherState


def _describe(signals: SignalInput) -> str:
    return describe(PreviewInput.from_classification(classify(signals), signals))


def _mature(**overrides) -> SignalInput:
    """A well-observed, large, unremarkable technology."""
    base = {
        "star_velocity_7d": 100.0,
        "star_velocity_28d": 100.0,
        "activity_velocity_7d": 10.0,
        "activity_velocity_28d": 10.0,
        "anomaly_z": 0.0,
        "volatility": 0.3,
        "stars_total": 80_000,
        "sample_days": 60,
        "repo_count": 5,
        "active_repo_count": 4,
        "age_days": 1500,
    }
    return SignalInput(**(base | overrides))


# --- The guarantee that matters most ---------------------------------------


@pytest.mark.parametrize("days", range(0, MIN_SAMPLE_DAYS))
def test_thin_history_is_stable_and_low_confidence(days):
    """Insufficient observation must never be dressed up as EMERGING.

    This is the single most important property: a brand-new technology with a
    handful of days of data looks explosive on any growth ratio.
    """
    result = classify(
        _mature(
            sample_days=days,
            star_velocity_7d=900.0,
            star_velocity_28d=10.0,
            anomaly_z=6.0,
            stars_total=400,
            age_days=20,
        )
    )
    assert result.state is WeatherState.STABLE
    assert result.confidence <= 0.25
    assert result.reason and "observation" in result.reason


def test_thin_history_reports_unknown_epistemically():
    result = classify(_mature(sample_days=2, active_repo_count=1))
    assert epistemic_status(result.confidence) is EpistemicStatus.UNKNOWN


# --- State assignment -------------------------------------------------------


def test_flat_signals_are_stable():
    result = classify(_mature())
    assert result.state is WeatherState.STABLE
    assert result.momentum == pytest.approx(0.0, abs=1e-6)


def test_large_base_accelerating_is_hot_not_emerging():
    result = classify(
        _mature(star_velocity_7d=300.0, anomaly_z=3.0, activity_velocity_7d=18.0)
    )
    assert result.state is WeatherState.HOT
    assert result.momentum > 0.5


def test_small_base_accelerating_is_emerging():
    result = classify(
        _mature(
            stars_total=2_000,
            age_days=180,
            star_velocity_7d=40.0,
            star_velocity_28d=10.0,
            anomaly_z=2.5,
        )
    )
    assert result.state is WeatherState.EMERGING


def test_decaying_against_own_baseline_is_cooling():
    result = classify(
        _mature(star_velocity_7d=30.0, star_velocity_28d=100.0, anomaly_z=-2.0)
    )
    assert result.state is WeatherState.COOLING
    assert result.momentum < 0


def test_discrete_event_outranks_trend_shape():
    """A major release is the explanation, even if the 28-day trend is flat."""
    result = classify(_mature(recent_event_magnitude=0.8))
    assert result.state is WeatherState.BREAKING


def test_incoherent_movement_is_storm_not_hot():
    result = classify(_mature(volatility=1.8, anomaly_z=2.6, star_velocity_7d=260.0))
    assert result.state is WeatherState.STORM


# --- Numeric invariants -----------------------------------------------------


@pytest.mark.parametrize(
    "signals",
    [
        SignalInput(),
        _mature(),
        _mature(star_velocity_7d=1e6, anomaly_z=99.0),
        _mature(star_velocity_7d=0.0, star_velocity_28d=1e6, anomaly_z=-99.0),
        _mature(star_velocity_7d=None, star_velocity_28d=None),
    ],
)
def test_outputs_satisfy_database_constraints(signals):
    """momentum in [-1,1] and confidence in [0,1] are CHECK constraints."""
    result = classify(signals)
    assert -1.0 <= result.momentum <= 1.0
    assert 0.0 <= result.confidence <= 1.0
    assert result.state in set(WeatherState)


def test_growth_ratio_is_scale_free():
    """A 200-star and a 200,000-star project doubling must score identically."""
    small = growth_ratio(20.0, 10.0)
    large = growth_ratio(20_000.0, 10_000.0)
    assert small == pytest.approx(large, rel=0.02)


def test_momentum_is_symmetric_about_no_change():
    up = compute_momentum(_mature(star_velocity_7d=200.0))
    down = compute_momentum(_mature(star_velocity_7d=50.0))
    assert up > 0 > down


def test_confidence_rises_with_history_and_breadth():
    thin = classify(_mature(sample_days=10, active_repo_count=1))
    thick = classify(_mature(sample_days=90, active_repo_count=5))
    assert thick.confidence > thin.confidence


def test_confidence_falls_with_volatility():
    steady = classify(_mature(volatility=0.1))
    erratic = classify(_mature(volatility=1.9))
    assert steady.confidence > erratic.confidence


# --- Explanation ------------------------------------------------------------


@pytest.mark.parametrize(
    "signals",
    [
        _mature(),
        _mature(star_velocity_7d=300.0, anomaly_z=3.0),
        _mature(star_velocity_7d=30.0, star_velocity_28d=100.0, anomaly_z=-2.0),
        _mature(recent_event_magnitude=0.9),
        _mature(volatility=1.8, anomaly_z=2.6),
        _mature(sample_days=1),
    ],
)
def test_explanation_is_a_single_plain_sentence(signals):
    text = _describe(signals)
    assert text
    assert text.endswith(".")
    assert "\n" not in text
    # One terminal full stop; decimals and separators must not add sentences.
    assert text.count(". ") == 0


def test_explanation_restates_measurements():
    signals = _mature(star_velocity_7d=300.0, anomaly_z=3.0)
    result = classify(signals)
    text = _describe(signals)
    assert "×" in text, "the sentence should quote the measured ratio"
    assert "σ" in text, "the sentence should quote the measured anomaly"
    assert epistemic_status(result.confidence) is EpistemicStatus.OBSERVATION


def test_thin_history_explanation_says_so_rather_than_narrating():
    text = _describe(_mature(sample_days=2, star_velocity_7d=900.0, anomaly_z=6.0))
    assert "day(s) of observation" in text
    assert "×" not in text, "no growth claim may be made on 2 days of data"
