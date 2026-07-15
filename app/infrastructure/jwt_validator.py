import time

import httpx
from jose import jwt
from jose.exceptions import JWTError

from app.domain.entities import AuthenticatedUser
from app.infrastructure.config import settings


class InvalidTokenError(Exception):
    pass


class EntraJwtValidator:
    """Validates inbound access tokens against Entra ID's JWKS.

    Keys are cached in-process with a TTL; Entra ID rotates signing keys
    infrequently so refetching on every request would be wasteful.
    """

    def __init__(self, jwks_ttl_seconds: int = 3600) -> None:
        self._jwks_ttl_seconds = jwks_ttl_seconds
        self._jwks_cache: dict | None = None
        self._jwks_fetched_at: float = 0.0

    async def _get_jwks(self) -> dict:
        now = time.monotonic()
        if self._jwks_cache is None or (now - self._jwks_fetched_at) > self._jwks_ttl_seconds:
            async with httpx.AsyncClient() as client:
                response = await client.get(settings.entra_jwks_uri)
                response.raise_for_status()
                self._jwks_cache = response.json()
                self._jwks_fetched_at = now
        return self._jwks_cache

    async def validate(self, token: str) -> AuthenticatedUser:
        jwks = await self._get_jwks()
        try:
            unverified_header = jwt.get_unverified_header(token)
            key = next(
                (k for k in jwks["keys"] if k["kid"] == unverified_header.get("kid")),
                None,
            )
            if key is None:
                raise InvalidTokenError("Signing key not found in JWKS")

            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                options={"verify_aud": False, "verify_iss": False},
            )
        except JWTError as exc:
            raise InvalidTokenError(str(exc)) from exc

        # Depending on the app registration's accessTokenAcceptedVersion
        # manifest setting, Entra ID issues either v1.0 tokens (issuer
        # sts.windows.net, aud = bare client id) or v2.0 tokens (issuer
        # login.microsoftonline.com/.../v2.0, aud = App ID URI). Accept both
        # rather than depending on that manifest setting being one specific
        # value.
        expected_audiences = {
            settings.entra_api_client_id,
            f"api://{settings.entra_api_client_id}",
        }
        expected_issuers = {
            settings.entra_issuer,
            f"https://sts.windows.net/{settings.entra_tenant_id}/",
        }
        if claims.get("aud") not in expected_audiences:
            raise InvalidTokenError(f"Unexpected audience: {claims.get('aud')!r}")
        if claims.get("iss") not in expected_issuers:
            raise InvalidTokenError(f"Unexpected issuer: {claims.get('iss')!r}")

        oid = claims.get("oid")
        if not oid:
            raise InvalidTokenError("Token missing 'oid' claim")

        return AuthenticatedUser(
            oid=oid,
            name=claims.get("name"),
            preferred_username=claims.get("preferred_username"),
        )


jwt_validator = EntraJwtValidator()
