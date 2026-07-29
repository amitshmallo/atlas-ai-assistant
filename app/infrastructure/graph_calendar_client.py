from datetime import datetime, timedelta, timezone

import httpx

from app.domain.entities import (
    CalendarEvent,
    CalendarEventCancelProposal,
    CalendarEventProposal,
    CalendarEventUpdateProposal,
    FreeBusyPeriod,
    FreeBusyResult,
)
from app.infrastructure.resilience import retry_graph_call

_GRAPH_EVENTS_URL = "https://graph.microsoft.com/v1.0/me/events"
_GRAPH_CALENDAR_VIEW_URL = "https://graph.microsoft.com/v1.0/me/calendarView"
_GRAPH_GET_SCHEDULE_URL = "https://graph.microsoft.com/v1.0/me/calendar/getSchedule"
_UPCOMING_WINDOW_DAYS = 30


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


class HttpxGraphCalendarClient:
    """Concrete implementation of domain.GraphCalendarClient. Only ever
    invoked by the explicit calendar-confirmation endpoint (app/api/routers
    /calendar.py) — never reachable from a model tool call directly."""

    # Deliberately not retried: a lost response after the write actually
    # succeeds server-side would retry into a duplicate event, sending a
    # second invite to every attendee. Graph doesn't support a client-
    # supplied idempotency key here, so a safe retry isn't possible without
    # a bigger change (e.g. checking for an existing event with the same
    # proposal details first).
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

    @retry_graph_call
    async def list_upcoming_events(self, access_token: str, top: int) -> list[CalendarEvent]:
        # calendarView (a date range query), not a $filter on /events —
        # Graph's plain /events list doesn't reliably support filtering by
        # date range; calendarView is the endpoint Microsoft's own docs
        # recommend for exactly this "what's on my calendar between X and Y"
        # case, and it also expands recurring events into their instances.
        now = datetime.now(timezone.utc)
        params: dict[str, str | int] = {
            "startDateTime": _iso(now),
            "endDateTime": _iso(now + timedelta(days=_UPCOMING_WINDOW_DAYS)),
            "$top": top,
            "$select": "id,subject,start,end",
            "$orderby": "start/dateTime",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                _GRAPH_CALENDAR_VIEW_URL,
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            data = response.json()

        return [
            CalendarEvent(
                id=item["id"],
                subject=item.get("subject", ""),
                start=item.get("start", {}).get("dateTime", ""),
                end=item.get("end", {}).get("dateTime", ""),
            )
            for item in data.get("value", [])
        ]

    # Deliberately not retried, same reasoning as create_event — a lost
    # response after Graph already applied the patch would retry into a
    # second identical patch, which is harmless here (PATCH is naturally
    # idempotent for a full-field replace) EXCEPT that Graph also emails
    # attendees an update notification per PATCH that changes time/subject
    # — a retry could send a confusing second "this event changed" email.
    async def update_event(self, access_token: str, proposal: CalendarEventUpdateProposal) -> CalendarEvent:
        body: dict = {}
        if proposal.subject is not None:
            body["subject"] = proposal.subject
        if proposal.start is not None:
            body["start"] = {"dateTime": proposal.start, "timeZone": "UTC"}
        if proposal.end is not None:
            body["end"] = {"dateTime": proposal.end, "timeZone": "UTC"}

        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{_GRAPH_EVENTS_URL}/{proposal.event_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                json=body,
            )
            response.raise_for_status()
            data = response.json()

        return CalendarEvent(
            id=data["id"],
            subject=data.get("subject", ""),
            start=data.get("start", {}).get("dateTime", ""),
            end=data.get("end", {}).get("dateTime", ""),
        )

    # Deliberately not retried: Graph's /cancel sends a cancellation email
    # to every attendee — a retry after a lost response would send a
    # second one.
    async def cancel_event(self, access_token: str, proposal: CalendarEventCancelProposal) -> None:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_GRAPH_EVENTS_URL}/{proposal.event_id}/cancel",
                headers={"Authorization": f"Bearer {access_token}"},
                json={},
            )
            response.raise_for_status()

    @retry_graph_call
    async def get_free_busy(
        self, access_token: str, emails: list[str], start: str, end: str
    ) -> list[FreeBusyResult]:
        body = {
            "schedules": emails,
            "startTime": {"dateTime": start, "timeZone": "UTC"},
            "endTime": {"dateTime": end, "timeZone": "UTC"},
            "availabilityViewInterval": 60,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                _GRAPH_GET_SCHEDULE_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                json=body,
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for schedule in data.get("value", []):
            busy_periods = [
                FreeBusyPeriod(
                    status=item.get("status", "busy"),
                    start=item.get("start", {}).get("dateTime", ""),
                    end=item.get("end", {}).get("dateTime", ""),
                )
                for item in schedule.get("scheduleItems", [])
            ]
            results.append(FreeBusyResult(email=schedule.get("scheduleId", ""), busy_periods=busy_periods))
        return results
