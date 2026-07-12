from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.auth_deps import AuthContext, get_auth_context
from app.api.deps import get_my_profile_use_case
from app.application.graph_profile import GetMyProfileUseCase
from app.domain.entities import UserProfile

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserProfile)
async def get_me(
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    use_case: Annotated[GetMyProfileUseCase, Depends(get_my_profile_use_case)],
) -> UserProfile:
    return await use_case.execute(
        user_oid=auth_context.user.oid,
        user_assertion=auth_context.raw_token,
    )
