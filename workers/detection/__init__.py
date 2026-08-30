"""Detection workers: turn raw daily facts into signals and events.

This is the DETECT stage of the product loop. Deterministic and statistical only —
no LLM. The classifier it drives lives in ``internetweather.analysis.weather_state``
and is already implemented and tested as a pure function.
"""
