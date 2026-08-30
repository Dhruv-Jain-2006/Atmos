"""Research endpoints — contract now, engine later.

These routes exist so the OpenAPI document, and therefore the generated frontend
client, is complete and stable. They return 501 until the research engine lands.
Declaring the contract early is what stops the frontend from inventing its own
shape and having to be rewritten.

Two properties are already fixed:

* Research is asynchronous — ``POST /api/research`` returns a job, never a result.
* Every finding carries an ``epistemic_status`` and its evidence.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status

from internetweather.schemas.research import (
    ChatReply,
    ChatRequest,
    ResearchJob,
    ResearchRequest,
    ResearchResult,
)

router = APIRouter(prefix="/api/research", tags=["research"])

NOT_YET = (
    "The research engine is not implemented in this slice. The contract is final; "
    "the implementation follows the first vertical slice."
)


def _unimplemented() -> HTTPException:
    return HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail=NOT_YET)


@router.post(
    "",
    response_model=ResearchJob,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue an investigation",
    responses={501: {"description": NOT_YET}},
)
def create(request: ResearchRequest) -> ResearchJob:
    """Returns immediately with a job. The frontend never blocks on research."""
    raise _unimplemented()


@router.get(
    "/{research_id}",
    response_model=ResearchResult,
    summary="Poll an investigation",
    responses={501: {"description": NOT_YET}},
)
def read(research_id: Annotated[str, Path(max_length=64)]) -> ResearchResult:
    raise _unimplemented()


@router.post(
    "/{research_id}/chat",
    response_model=ChatReply,
    summary="Ask the Research Copilot",
    responses={501: {"description": NOT_YET}},
)
def chat(
    research_id: Annotated[str, Path(max_length=64)], request: ChatRequest
) -> ChatReply:
    """Contextual to one research topic, grounded in Internet Weather data.

    Not a general-purpose chatbot: an answer it cannot ground in stored evidence
    is an answer it must decline to give.
    """
    raise _unimplemented()
