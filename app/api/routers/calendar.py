from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.auth_deps import AuthContext, get_auth_context
from app.api.deps import get_create_calendar_event_use_case
from app.application.create_calendar_event import CreateCalendarEventUseCase
from app.domain.entities import CalendarEvent, CalendarEventProposal

router = APIRouter(tags=["calendar"])


@router.post("/calendar/events", response_model=CalendarEvent)
async def confirm_calendar_event(
    proposal: CalendarEventProposal,
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    use_case: Annotated[CreateCalendarEventUseCase, Depends(get_create_calendar_event_use_case)],
) -> CalendarEvent:
    """The only path that actually creates a calendar event in Graph.
    Called directly by the frontend after the user reviews a proposal the
    assistant surfaced in chat — never triggered by the model itself."""
    return await use_case.execute(
        user_oid=auth_context.user.oid,
        user_assertion=auth_context.raw_token,
        proposal=proposal,
    )
