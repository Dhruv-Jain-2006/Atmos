"""Semantic vocabulary.

Served so the frontend renders weather states, subdomains and epistemic labels
from the API. Hardcoding a glyph in the UI is how a display drifts away from the
classifier that produced the value.
"""

from __future__ import annotations

from fastapi import APIRouter

from internetweather.enums import (
    WEATHER_STATE_META,
    EpistemicStatus,
    Subdomain,
    WeatherState,
)
from internetweather.schemas.common import SubdomainInfo, Vocabulary, WeatherStateInfo
from internetweather.universe import load_universe

router = APIRouter(tags=["meta"])


@router.get("/api/vocabulary", response_model=Vocabulary, summary="Semantic vocabulary")
def vocabulary() -> Vocabulary:
    try:
        universe = load_universe()
        labels = {key: meta.name for key, meta in universe.subdomains.items()}
    except (FileNotFoundError, ValueError):
        labels = {}

    return Vocabulary(
        weather_states=[
            WeatherStateInfo(state=member, **WEATHER_STATE_META[member])
            for member in WeatherState
        ],
        subdomains=[
            SubdomainInfo(
                key=key, label=labels.get(key, key.value.replace("_", " ").title())
            )
            for key in Subdomain
        ],
        epistemic_statuses=list(EpistemicStatus),
    )
