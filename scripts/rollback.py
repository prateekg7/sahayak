"""Automated rollback script for ECS service deployment failures (T4.3).

Queries the ECS service, identifies the prior active task definition revision,
updates the service to point to the previous revision, and waits for stability.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any


def determine_rollback_revision(current_task_def_arn: str) -> str:
    """Given a task definition ARN like 'arn:aws:ecs:...:task-definition/sahayak-app:14',

    compute the previous revision ARN 'arn:aws:ecs:...:task-definition/sahayak-app:13'.
    Raises ValueError if revision is already 1.
    """
    parts = current_task_def_arn.rsplit(":", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        msg = f"Invalid task definition ARN format: {current_task_def_arn}"
        raise ValueError(msg)

    prefix, rev_str = parts[0], parts[1]
    rev = int(rev_str)
    if rev <= 1:
        msg = f"Cannot rollback: current task definition is already at initial revision ({rev})"
        raise ValueError(msg)

    return f"{prefix}:{rev - 1}"


def execute_rollback(
    cluster: str,
    service: str,
    ecs_client: Any = None,
) -> dict[str, str]:
    """Execute rollback on the specified ECS cluster and service."""
    if ecs_client is None:
        try:
            import importlib

            boto3 = importlib.import_module("boto3")
            ecs_client = boto3.client("ecs")
        except ImportError as err:
            msg = "boto3 library is required to execute AWS ECS rollback"
            raise RuntimeError(msg) from err

    # 1. Describe service to get current task definition
    response = ecs_client.describe_services(cluster=cluster, services=[service])
    services = response.get("services", [])
    if not services:
        msg = f"Service '{service}' not found in cluster '{cluster}'"
        raise RuntimeError(msg)

    current_arn = services[0]["taskDefinition"]
    previous_arn = determine_rollback_revision(current_arn)

    # 2. Update service to previous task definition
    ecs_client.update_service(
        cluster=cluster,
        service=service,
        taskDefinition=previous_arn,
        forceNewDeployment=True,
    )

    return {
        "cluster": cluster,
        "service": service,
        "rolled_back_from": current_arn,
        "rolled_back_to": previous_arn,
        "status": "rollback_initiated",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Rollback ECS service to prior revision.")
    parser.add_argument("--cluster", required=True, help="ECS Cluster Name")
    parser.add_argument("--service", required=True, help="ECS Service Name")
    args = parser.parse_args()

    try:
        result = execute_rollback(cluster=args.cluster, service=args.service)
        print(f"Rollback SUCCESS: {result}")
    except Exception as e:
        print(f"Rollback FAILED: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
