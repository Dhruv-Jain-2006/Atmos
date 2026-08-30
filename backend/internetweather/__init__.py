"""Internet Weather — technology-intelligence platform.

Package layout mirrors the pipeline in CLAUDE.md:

    integrations/  external world in
    models/        normalized storage
    repositories/  data access
    analysis/      signals, weather-state classification
    services/      read orchestration for the API
    schemas/       API contracts
    api/           HTTP surface
    research/      investigation engine (later slice)
"""

__version__ = "0.1.0"
