"""Unit tests for continuous delivery scripts: smoke_test.py and rollback.py (T4.3)."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from scripts.rollback import determine_rollback_revision, execute_rollback
from scripts.smoke_test import run_smoke_test


def test_determine_rollback_revision() -> None:
    """Test computing the prior active revision from an ECS task definition ARN."""
    arn = "arn:aws:ecs:us-east-1:123456789012:task-definition/sahayak-app:14"
    prior = determine_rollback_revision(arn)
    assert prior == "arn:aws:ecs:us-east-1:123456789012:task-definition/sahayak-app:13"

    with pytest.raises(ValueError, match="already at initial revision"):
        determine_rollback_revision(
            "arn:aws:ecs:us-east-1:123456789012:task-definition/sahayak-app:1"
        )

    with pytest.raises(ValueError, match="Invalid task definition ARN format"):
        determine_rollback_revision("invalid-arn-without-colons")


def test_execute_rollback_success() -> None:
    """Test successful rollback invocation on mock ECS client."""
    mock_ecs = MagicMock()
    mock_ecs.describe_services.return_value = {
        "services": [
            {"taskDefinition": "arn:aws:ecs:us-east-1:123456789012:task-definition/sahayak-app:5"}
        ]
    }

    result = execute_rollback(
        cluster="sahayak-prod-cluster",
        service="sahayak-prod-app",
        ecs_client=mock_ecs,
    )

    assert result["status"] == "rollback_initiated"
    expected_arn = "arn:aws:ecs:us-east-1:123456789012:task-definition/sahayak-app:4"
    assert result["rolled_back_to"] == expected_arn
    mock_ecs.update_service.assert_called_once_with(
        cluster="sahayak-prod-cluster",
        service="sahayak-prod-app",
        taskDefinition=expected_arn,
        forceNewDeployment=True,
    )


def test_smoke_test_success() -> None:
    """Test smoke test passing when endpoints return 200 within latency limit."""
    mock_client = MagicMock(spec=httpx.Client)

    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.text = "OK"

    mock_client.get.return_value = mock_resp_200
    mock_client.post.return_value = mock_resp_200

    result = run_smoke_test(
        base_url="https://api.sahayak.app",
        iterations=3,
        max_latency_seconds=2.0,
        client=mock_client,
    )

    assert result["status"] == "healthy"
    assert result["iterations"] == 3


def test_smoke_test_failure_on_healthz() -> None:
    """Test smoke test raising RuntimeError when health check fails."""
    mock_client = MagicMock(spec=httpx.Client)

    mock_resp_500 = MagicMock()
    mock_resp_500.status_code = 500
    mock_resp_500.text = "Internal Server Error"

    mock_client.get.return_value = mock_resp_500

    with pytest.raises(RuntimeError, match="/healthz failed with status 500"):
        run_smoke_test(
            base_url="https://api.sahayak.app",
            iterations=1,
            client=mock_client,
        )
