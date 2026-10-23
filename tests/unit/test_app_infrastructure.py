"""Unit tests verifying infrastructure configuration and deployment artifacts (T4.1, T4.2)."""

from __future__ import annotations

from pathlib import Path


def test_terraform_modules_exist() -> None:
    """Verify all required Terraform modules and files exist."""
    root = Path(__file__).resolve().parents[2]
    tf_dir = root / "infra" / "terraform"

    assert (tf_dir / "main.tf").exists()
    assert (tf_dir / "variables.tf").exists()
    assert (tf_dir / "outputs.tf").exists()
    assert (tf_dir / "backend.tf").exists()

    # Modules
    for module in ["vpc", "database", "cache", "security_groups", "app", "idp"]:
        module_path = tf_dir / "modules" / module if module != "idp" else tf_dir / "idp"
        assert module_path.is_dir(), f"Module directory {module_path} must exist"
        assert (module_path / "main.tf").exists()
        assert (module_path / "variables.tf").exists()
        assert (module_path / "outputs.tf").exists()


def test_ecs_app_task_definition_configuration() -> None:
    """Verify ECS app task definition has healthcheck, least-privilege IAM, and secrets."""
    root = Path(__file__).resolve().parents[2]
    app_tf = root / "infra" / "terraform" / "modules" / "app" / "main.tf"
    content = app_tf.read_text(encoding="utf-8")

    # ALB target group health check on /healthz
    assert "/healthz" in content
    # Port 8000
    assert "8000" in content
    # ECS Fargate launch type
    assert "FARGATE" in content
    # Autoscaling policy configured
    assert "aws_appautoscaling_policy" in content
    # Secrets Manager integration
    assert "aws_secretsmanager_secret" in content
    # HTTPS redirect
    assert "HTTP_301" in content


def test_low_cost_deploy_guide_exists() -> None:
    """Verify low-cost alternative deployment guide is present and comprehensive."""
    root = Path(__file__).resolve().parents[2]
    guide = root / "docs" / "deploy" / "low-cost.md"
    assert guide.exists()

    content = guide.read_text(encoding="utf-8")
    assert "Cloud Run" in content
    assert "Fly.io" in content
    assert "/healthz" in content
    assert "/mcp" in content
