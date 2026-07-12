import time

import pytest
from jose import jwt

from app.infrastructure.config import settings
from app.infrastructure.jwt_validator import EntraJwtValidator, InvalidTokenError


@pytest.fixture()
def rsa_keypair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    public_numbers = public_key.public_numbers()
    return private_pem, public_numbers, private_key


def _jwk_from_public_numbers(public_numbers, kid: str) -> dict:
    from jose.utils import long_to_base64

    return {
        "kty": "RSA",
        "use": "sig",
        "kid": kid,
        "alg": "RS256",
        "n": long_to_base64(public_numbers.n).decode(),
        "e": long_to_base64(public_numbers.e).decode(),
    }


@pytest.fixture(autouse=True)
def entra_settings(monkeypatch):
    monkeypatch.setattr(settings, "entra_tenant_id", "test-tenant")
    monkeypatch.setattr(settings, "entra_api_client_id", "test-api-client")


async def test_validate_accepts_well_formed_token(monkeypatch, rsa_keypair):
    private_pem, public_numbers, _ = rsa_keypair
    kid = "test-kid"
    jwks = {"keys": [_jwk_from_public_numbers(public_numbers, kid)]}

    token = jwt.encode(
        {
            "oid": "user-oid-1",
            "name": "Julia Yoshpe",
            "preferred_username": "julia@example.com",
            "aud": settings.entra_api_client_id,
            "iss": settings.entra_issuer,
            "exp": int(time.time()) + 3600,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": kid},
    )

    validator = EntraJwtValidator()

    async def fake_get_jwks():
        return jwks

    monkeypatch.setattr(validator, "_get_jwks", fake_get_jwks)

    user = await validator.validate(token)

    assert user.oid == "user-oid-1"
    assert user.name == "Julia Yoshpe"
    assert user.preferred_username == "julia@example.com"


async def test_validate_rejects_token_with_wrong_audience(monkeypatch, rsa_keypair):
    private_pem, public_numbers, _ = rsa_keypair
    kid = "test-kid"
    jwks = {"keys": [_jwk_from_public_numbers(public_numbers, kid)]}

    token = jwt.encode(
        {
            "oid": "user-oid-1",
            "aud": "some-other-client",
            "iss": settings.entra_issuer,
            "exp": int(time.time()) + 3600,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": kid},
    )

    validator = EntraJwtValidator()

    async def fake_get_jwks():
        return jwks

    monkeypatch.setattr(validator, "_get_jwks", fake_get_jwks)

    with pytest.raises(InvalidTokenError):
        await validator.validate(token)


async def test_validate_rejects_token_signed_by_unknown_key(monkeypatch, rsa_keypair):
    private_pem, _, _ = rsa_keypair
    token = jwt.encode(
        {
            "oid": "user-oid-1",
            "aud": settings.entra_api_client_id,
            "iss": settings.entra_issuer,
            "exp": int(time.time()) + 3600,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "kid-not-in-jwks"},
    )

    validator = EntraJwtValidator()

    async def fake_get_jwks():
        return {"keys": []}

    monkeypatch.setattr(validator, "_get_jwks", fake_get_jwks)

    with pytest.raises(InvalidTokenError):
        await validator.validate(token)
