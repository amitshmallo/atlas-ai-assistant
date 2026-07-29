from app.domain.entities import CalendarEventCancelProposal
from app.domain.interfaces import GraphCalendarClient, GraphTokenProvider


class CancelCalendarEventUseCase:
    """Same confirm-only pattern as CreateCalendarEventUseCase: the model's
    `propose_cancel_event` tool never calls Graph itself — this only runs
    when the user explicitly confirms via a direct API call."""

    def __init__(self, token_provider: GraphTokenProvider, calendar_client: GraphCalendarClient) -> None:
        self._token_provider = token_provider
        self._calendar_client = calendar_client

    async def execute(self, user_oid: str, user_assertion: str, proposal: CalendarEventCancelProposal) -> None:
        graph_token = await self._token_provider.get_graph_token(user_oid, user_assertion)
        await self._calendar_client.cancel_event(graph_token, proposal)
