from typing import Annotated, NamedTuple

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.domain.entities import AuthenticatedUser
from app.infrastructure.jwt_validator import InvalidTokenError, jwt_validator

_bearer_scheme = HTTPBearer(auto_error=True)


class AuthContext(NamedTuple):
    """The validated identity plus the raw bearer token, which the OBO flow
    needs as the `user_assertion` to exchange for a Graph token."""

    user: AuthenticatedUser
    raw_token: str


async def get_auth_context(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
) -> AuthContext:
    try:
        user = await jwt_validator.validate(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return AuthContext(user=user, raw_token=credentials.credentials)


async def get_current_user(
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
) -> AuthenticatedUser:
    return auth_context.user
