import httpx

from app.domain.entities import CalendarEvent, CalendarEventProposal

_GRAPH_EVENTS_URL = "https://graph.microsoft.com/v1.0/me/events"


class HttpxGraphCalendarClient:
    """Concrete implementation of domain.GraphCalendarClient. Only ever
    invoked by the explicit calendar-confirmation endpoint (app/api/routers
    /calendar.py) — never reachable from a model tool call directly."""

    async def create_event(self, access_token: str, proposal: CalendarEventProposal) -> CalendarEvent:
        body = {
            "subject": proposal.subject,
            "start": {"dateTime": proposal.start, "timeZone": "UTC"},
            "end": {"dateTime": proposal.end, "timeZone": "UTC"},
            "attendees": [
                {"emailAddress": {"address": attendee}, "type": "required"}
                for attendee in proposal.attendees
            ],
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                _GRAPH_EVENTS_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                json=body,
            )
            response.raise_for_status()
            data = response.json()

        return CalendarEvent(
            id=data["id"],
            subject=data.get("subject", proposal.subject),
            start=proposal.start,
            end=proposal.end,
        )
