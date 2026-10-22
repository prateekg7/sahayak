"""Unit tests for JWT validation, JWKS caching, and key rotation."""

from __future__ import annotations

import json
import time
from typing import Any

import fakeredis.aioredis
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from sahayak.core.auth.jwt import (
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    InvalidTokenError,
    JWKSFetchError,
    JWTValidator,
    KeyNotFoundError,
    TokenExpiredError,
)
from sahayak.core.cache import Cache


@pytest.fixture(scope="module")
def rsa_key_1() -> rsa.RSAPrivateKey:
    """Generate first RSA test key."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def rsa_key_2() -> rsa.RSAPrivateKey:
    """Generate second RSA test key for key rotation and signature mismatch."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_jwk(key: rsa.RSAPrivateKey, kid: str) -> dict[str, Any]:
    """Convert RSA public key to JWK dictionary."""
    jwk_dict: dict[str, Any] = dict(json.loads(RSAAlgorithm.to_jwk(key.public_key())))
    jwk_dict["kid"] = kid
    return jwk_dict


def make_token(
    key: rsa.RSAPrivateKey,
    kid: str,
    *,
    sub: str = "user-123",
    iss: str = "https://auth.example.com",
    aud: str = "sahayak-api",
    exp_offset: int = 3600,
    scope: str = "academics.read academics.write",
    alg: str = "RS256",
) -> str:
    """Generate a signed JWT token for testing."""
    now = int(time.time())
    payload = {
        "sub": sub,
        "iss": iss,
        "aud": aud,
        "exp": now + exp_offset,
        "iat": now,
        "nbf": now,
        "scope": scope,
    }
    return jwt.encode(payload, key, algorithm=alg, headers={"kid": kid})


@pytest.mark.asyncio
async def test_jwt_validation_success(rsa_key_1: rsa.RSAPrivateKey) -> None:
    """A valid JWT with matching claims is decoded and returns TokenClaims."""
    jwks = {"keys": [make_jwk(rsa_key_1, "key-1")]}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=jwks)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        validator = JWTValidator(
            issuer="https://auth.example.com",
            audience="sahayak-api",
            jwks_url="https://auth.example.com/.well-known/jwks.json",
            http_client=http_client,
        )

        token = make_token(rsa_key_1, "key-1", sub="sub-valid-user")
        claims = await validator.validate_token(token)

        assert claims.subject == "sub-valid-user"
        assert claims.issuer == "https://auth.example.com"
        assert claims.audience == "sahayak-api"
        assert "academics.read" in claims.scopes
        assert "academics.write" in claims.scopes


@pytest.mark.asyncio
async def test_jwt_validation_expired(rsa_key_1: rsa.RSAPrivateKey) -> None:
    """A token expired beyond the 60s clock skew window raises TokenExpiredError."""
    jwks = {"keys": [make_jwk(rsa_key_1, "key-1")]}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=jwks))

    async with httpx.AsyncClient(transport=transport) as http_client:
        validator = JWTValidator(
            issuer="https://auth.example.com",
            audience="sahayak-api",
            jwks_url="https://auth.example.com/.well-known/jwks.json",
            http_client=http_client,
        )

        # Expired 120 seconds ago (> 60s skew)
        token = make_token(rsa_key_1, "key-1", exp_offset=-120)
        with pytest.raises(TokenExpiredError, match="expired"):
            await validator.validate_token(token)


@pytest.mark.asyncio
async def test_jwt_validation_wrong_audience(rsa_key_1: rsa.RSAPrivateKey) -> None:
    """A token targeting a different audience raises InvalidAudienceError."""
    jwks = {"keys": [make_jwk(rsa_key_1, "key-1")]}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=jwks))

    async with httpx.AsyncClient(transport=transport) as http_client:
        validator = JWTValidator(
            issuer="https://auth.example.com",
            audience="sahayak-api",
            jwks_url="https://auth.example.com/.well-known/jwks.json",
            http_client=http_client,
        )

        token = make_token(rsa_key_1, "key-1", aud="wrong-audience")
        with pytest.raises(InvalidAudienceError):
            await validator.validate_token(token)


@pytest.mark.asyncio
async def test_jwt_validation_wrong_issuer(rsa_key_1: rsa.RSAPrivateKey) -> None:
    """A token issued by an untrusted issuer raises InvalidIssuerError."""
    jwks = {"keys": [make_jwk(rsa_key_1, "key-1")]}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=jwks))

    async with httpx.AsyncClient(transport=transport) as http_client:
        validator = JWTValidator(
            issuer="https://auth.example.com",
            audience="sahayak-api",
            jwks_url="https://auth.example.com/.well-known/jwks.json",
            http_client=http_client,
        )

        token = make_token(rsa_key_1, "key-1", iss="https://evil.example.com")
        with pytest.raises(InvalidIssuerError):
            await validator.validate_token(token)


@pytest.mark.asyncio
async def test_jwt_validation_bad_signature(
    rsa_key_1: rsa.RSAPrivateKey, rsa_key_2: rsa.RSAPrivateKey
) -> None:
    """A token signed by a different key raises InvalidSignatureError."""
    # JWKS advertises key_1 for "key-1"
    jwks = {"keys": [make_jwk(rsa_key_1, "key-1")]}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=jwks))

    async with httpx.AsyncClient(transport=transport) as http_client:
        validator = JWTValidator(
            issuer="https://auth.example.com",
            audience="sahayak-api",
            jwks_url="https://auth.example.com/.well-known/jwks.json",
            http_client=http_client,
        )

        # Token signed with key_2 but claiming kid="key-1"
        token = make_token(rsa_key_2, "key-1")
        with pytest.raises(InvalidSignatureError):
            await validator.validate_token(token)


@pytest.mark.asyncio
async def test_jwt_validation_unknown_kid(rsa_key_1: rsa.RSAPrivateKey) -> None:
    """A token with an unknown key identifier raises KeyNotFoundError."""
    jwks = {"keys": [make_jwk(rsa_key_1, "key-1")]}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=jwks))

    async with httpx.AsyncClient(transport=transport) as http_client:
        validator = JWTValidator(
            issuer="https://auth.example.com",
            audience="sahayak-api",
            jwks_url="https://auth.example.com/.well-known/jwks.json",
            http_client=http_client,
        )

        token = make_token(rsa_key_1, "key-nonexistent")
        with pytest.raises(KeyNotFoundError, match="No matching JWK found"):
            await validator.validate_token(token)


@pytest.mark.asyncio
async def test_jwt_validation_key_rotation(
    rsa_key_1: rsa.RSAPrivateKey, rsa_key_2: rsa.RSAPrivateKey
) -> None:
    """A new kid triggers JWKS refresh and successfully validates the rotated key."""
    call_count = 0

    def rotating_handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Initial JWKS only has key 1
            return httpx.Response(200, json={"keys": [make_jwk(rsa_key_1, "key-1")]})
        # After rotation, key 2 is added
        return httpx.Response(
            200,
            json={"keys": [make_jwk(rsa_key_1, "key-1"), make_jwk(rsa_key_2, "key-2")]},
        )

    transport = httpx.MockTransport(rotating_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        validator = JWTValidator(
            issuer="https://auth.example.com",
            audience="sahayak-api",
            jwks_url="https://auth.example.com/.well-known/jwks.json",
            http_client=http_client,
        )

        # First request populates initial cache
        token1 = make_token(rsa_key_1, "key-1")
        await validator.validate_token(token1)
        assert call_count == 1

        # Second request uses rotated key-2; triggers refresh and succeeds
        token2 = make_token(rsa_key_2, "key-2")
        claims2 = await validator.validate_token(token2)
        assert claims2.subject == "user-123"
        assert call_count == 2


@pytest.mark.asyncio
async def test_jwt_validation_malformed_and_disallowed_algorithms() -> None:
    """Malformed tokens and disallowed algorithms (none, HS256) are rejected."""
    validator = JWTValidator(
        issuer="https://auth.example.com",
        audience="sahayak-api",
        jwks_url="https://auth.example.com/.well-known/jwks.json",
    )

    with pytest.raises(InvalidTokenError, match="Malformed"):
        await validator.validate_token("not-a-token")

    # Symmetric HS256 token must be rejected by algorithm check
    hs256_token = jwt.encode(
        {"sub": "123", "iss": "https://auth.example.com", "exp": int(time.time()) + 3600},
        "a" * 32,
        algorithm="HS256",
        headers={"kid": "hs256-key"},
    )
    with pytest.raises(InvalidTokenError, match="Algorithm 'HS256' is not in allowed"):
        await validator.validate_token(hs256_token)


@pytest.mark.asyncio
async def test_jwt_jwks_fetch_error(rsa_key_1: rsa.RSAPrivateKey) -> None:
    """HTTP error fetching JWKS raises JWKSFetchError."""
    transport = httpx.MockTransport(lambda _: httpx.Response(500))

    async with httpx.AsyncClient(transport=transport) as http_client:
        validator = JWTValidator(
            jwks_url="https://auth.example.com/.well-known/jwks.json",
            http_client=http_client,
        )
        token = make_token(rsa_key_1, "1")
        with pytest.raises(JWKSFetchError):
            await validator.validate_token(token)


@pytest.mark.asyncio
async def test_jwt_caching_in_redis(rsa_key_1: rsa.RSAPrivateKey) -> None:
    """JWKS keys are stored in and retrieved from the Redis cache."""
    jwks = {"keys": [make_jwk(rsa_key_1, "key-1")]}
    call_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=jwks)

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache = Cache(fake_redis, namespace="test_jwks")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        validator = JWTValidator(
            issuer="https://auth.example.com",
            audience="sahayak-api",
            jwks_url="https://auth.example.com/.well-known/jwks.json",
            cache=cache,
            http_client=http_client,
        )

        token = make_token(rsa_key_1, "key-1")
        await validator.validate_token(token)
        assert call_count == 1

        # A new validator with empty local cache but the same Redis cache
        validator2 = JWTValidator(
            issuer="https://auth.example.com",
            audience="sahayak-api",
            jwks_url="https://auth.example.com/.well-known/jwks.json",
            cache=cache,
            http_client=http_client,
        )
        await validator2.validate_token(token)
        # Should not have called HTTP handler again; hit Redis cache
        assert call_count == 1


@pytest.mark.asyncio
async def test_jwt_unconfigured_jwks_url(rsa_key_1: rsa.RSAPrivateKey) -> None:
    """Attempting to validate when jwks_url is None raises JWKSFetchError."""
    validator = JWTValidator(jwks_url=None)
    token = make_token(rsa_key_1, "1")
    with pytest.raises(JWKSFetchError, match="not configured"):
        await validator.validate_token(token)


@pytest.mark.asyncio
async def test_jwt_single_key_without_kid(rsa_key_1: rsa.RSAPrivateKey) -> None:
    """A token without kid header can be validated if JWKS contains exactly one key."""
    jwks = {"keys": [make_jwk(rsa_key_1, "key-single")]}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=jwks))

    async with httpx.AsyncClient(transport=transport) as http_client:
        validator = JWTValidator(
            issuer="https://auth.example.com",
            audience="sahayak-api",
            jwks_url="https://auth.example.com/.well-known/jwks.json",
            http_client=http_client,
        )

        now = int(time.time())
        token_payload = {
            "sub": "u-single",
            "iss": "https://auth.example.com",
            "aud": "sahayak-api",
            "exp": now + 3600,
        }
        token = jwt.encode(token_payload, rsa_key_1, algorithm="RS256")
        claims = await validator.validate_token(token)
        assert claims.subject == "u-single"


@pytest.mark.asyncio
async def test_jwt_alternative_scope_claims(rsa_key_1: rsa.RSAPrivateKey) -> None:
    """Tokens with scp list or permissions list claims have scopes extracted."""
    jwks = {"keys": [make_jwk(rsa_key_1, "key-1")]}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=jwks))

    async with httpx.AsyncClient(transport=transport) as http_client:
        validator = JWTValidator(
            issuer="https://auth.example.com",
            audience="sahayak-api",
            jwks_url="https://auth.example.com/.well-known/jwks.json",
            http_client=http_client,
        )

        now = int(time.time())
        payload_scp = {
            "sub": "u-scp",
            "iss": "https://auth.example.com",
            "aud": "sahayak-api",
            "exp": now + 3600,
            "scp": ["scope1", "scope2"],
        }
        token_scp = jwt.encode(
            payload_scp,
            rsa_key_1,
            algorithm="RS256",
            headers={"kid": "key-1"},
        )
        claims_scp = await validator.validate_token(token_scp)
        assert claims_scp.scopes == ("scope1", "scope2")

        payload_perm = {
            "sub": "u-perm",
            "iss": "https://auth.example.com",
            "aud": "sahayak-api",
            "exp": now + 3600,
            "permissions": ["perm1"],
        }
        token_perm = jwt.encode(
            payload_perm,
            rsa_key_1,
            algorithm="RS256",
            headers={"kid": "key-1"},
        )
        claims_perm = await validator.validate_token(token_perm)
        assert claims_perm.scopes == ("perm1",)


@pytest.mark.asyncio
async def test_jwt_invalid_jwk_structure(rsa_key_1: rsa.RSAPrivateKey) -> None:
    """Malformed JWK key raises InvalidTokenError."""
    jwks = {"keys": [{"kid": "key-bad", "kty": "RSA"}]}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=jwks))

    async with httpx.AsyncClient(transport=transport) as http_client:
        validator = JWTValidator(
            jwks_url="https://auth.example.com/.well-known/jwks.json",
            http_client=http_client,
        )
        token = make_token(rsa_key_1, "key-bad")
        with pytest.raises(InvalidTokenError, match="Failed to parse JWK"):
            await validator.validate_token(token)
