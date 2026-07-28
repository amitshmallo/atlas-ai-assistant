from app.domain.entities import UsageSummary
from app.domain.interfaces import UsageRepository
from app.infrastructure.config import settings


class GetUsageSummaryUseCase:
    """Depends only on domain.UsageRepository. Cost is estimated from
    configured per-1k-token rates, not fetched from Azure billing — good
    enough for an at-a-glance usage panel, not for invoicing."""

    def __init__(self, usage_repository: UsageRepository) -> None:
        self._usage_repository = usage_repository

    async def execute(self, user_oid: str, since_days: int = 30) -> UsageSummary:
        prompt_tokens, completion_tokens, turn_count = await self._usage_repository.get_summary(
            user_oid, since_days
        )
        cost = (
            prompt_tokens / 1000 * settings.azure_openai_input_cost_per_1k
            + completion_tokens / 1000 * settings.azure_openai_output_cost_per_1k
        )
        return UsageSummary(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            estimated_cost_usd=round(cost, 4),
            turn_count=turn_count,
        )
