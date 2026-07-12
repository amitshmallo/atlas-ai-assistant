from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.deps import get_health_status_use_case
from app.application.health import GetHealthStatusUseCase
from app.domain.entities import HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus)
async def get_health(
    response: Response,
    use_case: Annotated[GetHealthStatusUseCase, Depends(get_health_status_use_case)],
) -> HealthStatus:
    status = await use_case.execute()
    response.status_code = 200 if status.healthy else 503
    return status
