"""Token fuzzing security tests (T1.9)."""

from __future__ import annotations

import json
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from sahayak.core.auth.jwt import JWTValidator
from sahayak.main import create_app


@pytest.fixture(scope="module")
def fuzz_rsa_key() -> rsa.RSAPrivateKey:
    """RSA key for token fuzzing tests."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.mark.asyncio
async def test_token_fuzzing_matrix(fuzz_rsa_key: rsa.RSAPrivateKey) -> None:
    """All invalid, corrupted, fuzzed, or non-compliant tokens return 401 with no leaks."""
    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(fuzz_rsa_key.public_key())))
    jwk_dict["kid"] = "fuzz-key-1"
    jwks = {"keys": [jwk_dict]}

    transport_mock = httpx.MockTransport(lambda _: httpx.Response(200, json=jwks))
    async with httpx.AsyncClient(transport=transport_mock) as http_client:
        validator = JWTValidator(
            issuer="https://auth.example.com",
            audience="sahayak-api",
            jwks_url="https://auth.example.com/.well-known/jwks.json",
            http_client=http_client,
        )
        app = create_app(enable_mcp=False, jwt_validator=validator)

        now = int(time.time())

        # Construct fuzzed tokens
        expired_token = jwt.encode(
            {
                "sub": "u1",
                "iss": "https://auth.example.com",
                "aud": "sahayak-api",
                "exp": now - 300,
            },
            fuzz_rsa_key,
            algorithm="RS256",
            headers={"kid": "fuzz-key-1"},
        )
        future_nbf_token = jwt.encode(
            {
                "sub": "u1",
                "iss": "https://auth.example.com",
                "aud": "sahayak-api",
                "exp": now + 3600,
                "nbf": now + 600,
            },
            fuzz_rsa_key,
            algorithm="RS256",
            headers={"kid": "fuzz-key-1"},
        )
        wrong_iss_token = jwt.encode(
            {"sub": "u1", "iss": "https://attacker.com", "aud": "sahayak-api", "exp": now + 3600},
            fuzz_rsa_key,
            algorithm="RS256",
            headers={"kid": "fuzz-key-1"},
        )
        wrong_aud_token = jwt.encode(
            {"sub": "u1", "iss": "https://auth.example.com", "aud": "other-api", "exp": now + 3600},
            fuzz_rsa_key,
            algorithm="RS256",
            headers={"kid": "fuzz-key-1"},
        )
        none_alg_token = jwt.encode(
            {
                "sub": "u1",
                "iss": "https://auth.example.com",
                "aud": "sahayak-api",
                "exp": now + 3600,
            },
            key="",
            algorithm="none",
        )
        hs256_token = jwt.encode(
            {
                "sub": "u1",
                "iss": "https://auth.example.com",
                "aud": "sahayak-api",
                "exp": now + 3600,
            },
            key="symmetric-secret-key-too-short",
            algorithm="HS256",
            headers={"kid": "fuzz-key-1"},
        )
        tampered_token = expired_token[:-4] + "dead"

        fuzz_cases = [
            ("garbage_ascii", "not-a-token-at-all"),
            ("truncated_header", "eyJhbGciOiJSUzI1NiJ9"),
            ("invalid_base64", "!!!.@@@.###"),
            ("expired_token", expired_token),
            ("future_nbf_token", future_nbf_token),
            ("wrong_iss_token", wrong_iss_token),
            ("wrong_aud_token", wrong_aud_token),
            ("alg_none", none_alg_token),
            ("symmetric_hs256", hs256_token),
            ("tampered_signature", tampered_token),
        ]

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            for case_name, token in fuzz_cases:
                headers = {"Authorization": f"Bearer {token}"}
                res = await client.get("/healthz", headers=headers)
                assert res.status_code == 401, (
                    f"Case {case_name} expected 401, got {res.status_code}"
                )
                assert "WWW-Authenticate" not in res.headers, (
                    f"Case {case_name} leaked WWW-Authenticate"
                )
                assert "Traceback" not in res.text, f"Case {case_name} leaked traceback: {res.text}"
