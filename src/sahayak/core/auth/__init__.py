"""Authentication, JWT validation, and principal resolution."""

from sahayak.core.auth.jwt import (
    ALLOWED_ALGORITHMS,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    InvalidTokenError,
    JWKSFetchError,
    JWTValidationError,
    JWTValidator,
    KeyNotFoundError,
    TokenClaims,
    TokenExpiredError,
)
from sahayak.core.auth.middleware import AuthMiddleware
from sahayak.core.auth.principal import (
    Principal,
    allow_anonymous,
    get_current_principal,
    requires,
    reset_current_principal,
    set_current_principal,
)

__all__ = [
    "ALLOWED_ALGORITHMS",
    "AuthMiddleware",
    "InvalidAudienceError",
    "InvalidIssuerError",
    "InvalidSignatureError",
    "InvalidTokenError",
    "JWKSFetchError",
    "JWTValidationError",
    "JWTValidator",
    "KeyNotFoundError",
    "Principal",
    "TokenClaims",
    "TokenExpiredError",
    "allow_anonymous",
    "get_current_principal",
    "requires",
    "reset_current_principal",
    "set_current_principal",
]
