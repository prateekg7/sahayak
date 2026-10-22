"""JWT validation and JWKS key management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
import jwt
from jwt import PyJWK
from jwt.types import Options

if TYPE_CHECKING:
    from sahayak.core.cache import Cache

ALLOWED_ALGORITHMS: tuple[str, ...] = (
    "RS256",
    "RS384",
    "RS512",
    "ES256",
    "ES384",
    "ES512",
)


class JWTValidationError(Exception):
    """Base exception for all JWT validation and retrieval failures."""


class TokenExpiredError(JWTValidationError):
    """Token has expired beyond the allowable clock skew."""


class InvalidTokenError(JWTValidationError):
    """Token is malformed or violates syntactic constraints."""


class InvalidSignatureError(JWTValidationError):
    """Cryptographic signature validation failed."""


class InvalidIssuerError(JWTValidationError):
    """Token issuer does not match configured issuer."""


class InvalidAudienceError(JWTValidationError):
    """Token audience does not match configured audience."""


class KeyNotFoundError(JWTValidationError):
    """Matching key identifier not found in the JWKS."""


class JWKSFetchError(JWTValidationError):
    """Failure fetching JWKS from external endpoint."""


@dataclass(frozen=True)
class TokenClaims:
    """Validated claims extracted from an external JWT."""

    subject: str
    issuer: str
    audience: str | list[str]
    scopes: tuple[str, ...]
    expires_at: int
    raw: dict[str, Any]


class JWTValidator:
    """Validates external identity provider JWTs with JWKS caching and key rotation."""

    def __init__(
        self,
        *,
        issuer: str | None = None,
        audience: str | None = None,
        jwks_url: str | None = None,
        cache: Cache | None = None,
        http_client: httpx.AsyncClient | None = None,
        allowed_algorithms: tuple[str, ...] = ALLOWED_ALGORITHMS,
        leeway_seconds: int = 60,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._jwks_url = jwks_url
        self._cache = cache
        self._http_client = http_client
        self._allowed_algorithms = allowed_algorithms
        self._leeway_seconds = leeway_seconds
        self._local_jwks_cache: dict[str, Any] | None = None

    async def _fetch_jwks(self) -> dict[str, Any]:
        """Fetch JWKS keys from the configured endpoint."""
        if not self._jwks_url:
            msg = "JWKS URL is not configured"
            raise JWKSFetchError(msg)

        try:
            if self._http_client:
                response = await self._http_client.get(self._jwks_url)
                response.raise_for_status()
                return response.json()  # type: ignore[no-any-return]

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(self._jwks_url)
                response.raise_for_status()
                return response.json()  # type: ignore[no-any-return]
        except Exception as exc:
            msg = f"Failed to fetch JWKS from {self._jwks_url}: {exc}"
            raise JWKSFetchError(msg) from exc

    async def _get_jwks(self, force_refresh: bool = False) -> dict[str, Any]:
        """Retrieve JWKS keys from cache or fetch remote JWKS on miss or refresh."""
        cache_key = f"jwks:{self._jwks_url}"

        if not force_refresh:
            if self._local_jwks_cache is not None:
                return self._local_jwks_cache

            if self._cache:
                cached = await self._cache.get_json(cache_key)
                if isinstance(cached, dict):
                    self._local_jwks_cache = cached
                    return cached

        jwks = await self._fetch_jwks()
        self._local_jwks_cache = jwks

        if self._cache:
            # Cache JWKS for 1 hour
            await self._cache.set_json(cache_key, jwks, ttl_seconds=3600)

        return jwks

    async def _resolve_key(self, kid: str | None) -> Any:
        """Find the matching public key in the JWKS, triggering key rotation on miss."""
        jwks = await self._get_jwks(force_refresh=False)
        keys: list[dict[str, Any]] = jwks.get("keys", [])

        # Check existing cached keys
        matched_jwk = next((k for k in keys if k.get("kid") == kid), None) if kid else None

        # Key rotation handling: if not found, refresh JWKS once
        if matched_jwk is None and kid is not None:
            refreshed_jwks = await self._get_jwks(force_refresh=True)
            refreshed_keys: list[dict[str, Any]] = refreshed_jwks.get("keys", [])
            matched_jwk = next((k for k in refreshed_keys if k.get("kid") == kid), None)

        if matched_jwk is None:
            if not kid and len(keys) == 1:
                matched_jwk = keys[0]
            else:
                msg = f"No matching JWK found for kid '{kid}'"
                raise KeyNotFoundError(msg)

        try:
            pyjwk = PyJWK.from_dict(matched_jwk)
            return pyjwk.key
        except Exception as exc:
            msg = f"Failed to parse JWK key: {exc}"
            raise InvalidTokenError(msg) from exc

    async def validate_token(self, token: str) -> TokenClaims:
        """Validate a JWT bearer token and return extracted claims.

        Raises:
            TokenExpiredError: If token expired outside clock skew.
            InvalidSignatureError: If cryptographic signature is invalid.
            InvalidIssuerError: If issuer does not match.
            InvalidAudienceError: If audience does not match.
            KeyNotFoundError: If key ID cannot be resolved.
            InvalidTokenError: If token is malformed or invalid.
        """
        try:
            header = jwt.get_unverified_header(token)
        except Exception as exc:
            msg = f"Malformed token header: {exc}"
            raise InvalidTokenError(msg) from exc

        alg = header.get("alg")
        if not alg or alg not in self._allowed_algorithms:
            msg = f"Algorithm '{alg}' is not in allowed algorithms"
            raise InvalidTokenError(msg)

        kid = header.get("kid")
        public_key = await self._resolve_key(kid)

        options: Options = {
            "verify_signature": True,
            "verify_exp": True,
            "verify_nbf": True,
            "verify_iat": True,
            "verify_aud": self._audience is not None,
            "verify_iss": self._issuer is not None,
            "require": ["exp", "iss", "sub"],
        }

        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                key=public_key,
                algorithms=list(self._allowed_algorithms),
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway_seconds,
                options=options,
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenExpiredError("Token has expired") from exc
        except jwt.InvalidIssuerError as exc:
            raise InvalidIssuerError("Token issuer does not match") from exc
        except jwt.InvalidAudienceError as exc:
            raise InvalidAudienceError("Token audience does not match") from exc
        except jwt.InvalidSignatureError as exc:
            raise InvalidSignatureError("Token signature is invalid") from exc
        except jwt.InvalidTokenError as exc:
            raise InvalidTokenError(f"Invalid token: {exc}") from exc

        # Parse scopes from scope or scp or permissions
        scopes_list: list[str] = []
        if "scope" in payload and isinstance(payload["scope"], str):
            scopes_list.extend(payload["scope"].split())
        elif "scp" in payload and isinstance(payload["scp"], list):
            scopes_list.extend(str(s) for s in payload["scp"])
        elif "permissions" in payload and isinstance(payload["permissions"], list):
            scopes_list.extend(str(s) for s in payload["permissions"])

        return TokenClaims(
            subject=str(payload["sub"]),
            issuer=str(payload["iss"]),
            audience=payload.get("aud", ""),
            scopes=tuple(scopes_list),
            expires_at=int(payload["exp"]),
            raw=payload,
        )
