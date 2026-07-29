from app.domain.entities import CalendarEvent, CalendarEventUpdateProposal
from app.domain.interfaces import GraphCalendarClient, GraphTokenProvider


class UpdateCalendarEventUseCase:
    """Same confirm-only pattern as CreateCalendarEventUseCase: the model's
    `propose_reschedule_event` tool never calls Graph itself — this only
    runs when the user explicitly confirms via a direct API call."""

    def __init__(self, token_provider: GraphTokenProvider, calendar_client: GraphCalendarClient) -> None:
        self._token_provider = token_provider
        self._calendar_client = calendar_client

    async def execute(
        self, user_oid: str, user_assertion: str, proposal: CalendarEventUpdateProposal
    ) -> CalendarEvent:
        graph_token = await self._token_provider.get_graph_token(user_oid, user_assertion)
        return await self._calendar_client.update_event(graph_token, proposal)
