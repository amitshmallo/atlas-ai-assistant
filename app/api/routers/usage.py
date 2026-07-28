from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.auth_deps import AuthContext, get_auth_context
from app.api.deps import get_usage_summary_use_case
from app.application.get_usage_summary import GetUsageSummaryUseCase
from app.domain.entities import UsageSummary

router = APIRouter(tags=["usage"])


@router.get("/usage/summary")
async def get_usage_summary(
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    use_case: Annotated[GetUsageSummaryUseCase, Depends(get_usage_summary_use_case)],
) -> UsageSummary:
    return await use_case.execute(auth_context.user.oid)
