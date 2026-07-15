from app.domain.entities import CalendarEvent, CalendarEventProposal
from app.domain.interfaces import GraphCalendarClient, GraphTokenProvider


class CreateCalendarEventUseCase:
    """Exchanges the caller's JWT for a Graph token (On-Behalf-Of), then
    actually creates the event. This is the only path that can create a
    calendar event — the model's `propose_calendar_event` tool never calls
    Graph itself, so this use case only runs when the user explicitly
    confirms via a direct API call, not as a side effect of chat."""

    def __init__(
        self,
        token_provider: GraphTokenProvider,
        calendar_client: GraphCalendarClient,
    ) -> None:
        self._token_provider = token_provider
        self._calendar_client = calendar_client

    async def execute(
        self, user_oid: str, user_assertion: str, proposal: CalendarEventProposal
    ) -> CalendarEvent:
        graph_token = await self._token_provider.get_graph_token(user_oid, user_assertion)
        return await self._calendar_client.create_event(graph_token, proposal)
