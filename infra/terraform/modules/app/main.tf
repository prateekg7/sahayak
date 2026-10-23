# 1. ECR Container Repository
resource "aws_ecr_repository" "sahayak" {
  name                 = "sahayak-${var.environment}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name        = "sahayak-${var.environment}-ecr"
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

resource "aws_ecr_lifecycle_policy" "sahayak" {
  repository = aws_ecr_repository.sahayak.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 30 tagged production images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 30
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# 2. CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/sahayak-${var.environment}-app"
  retention_in_days = var.environment == "prod" ? 30 : 14

  tags = {
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/sahayak-${var.environment}-worker"
  retention_in_days = var.environment == "prod" ? 30 : 14

  tags = {
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

# 3. Secrets Manager Secret
resource "aws_secretsmanager_secret" "app" {
  name                    = "sahayak-${var.environment}-app-secrets"
  recovery_window_in_days = var.environment == "prod" ? 30 : 0

  tags = {
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

# 4. IAM Roles for ECS Execution and Task
resource "aws_iam_role" "ecs_execution_role" {
  name = "sahayak-${var.environment}-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution_default" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_policy" "ecs_secrets_access" {
  name        = "sahayak-${var.environment}-ecs-secrets-policy"
  description = "Allows ECS tasks to read Secrets Manager secrets"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [aws_secretsmanager_secret.app.arn]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_secrets_attach" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = aws_iam_policy.ecs_secrets_access.arn
}

resource "aws_iam_role" "ecs_task_role" {
  name = "sahayak-${var.environment}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

# 5. Application Load Balancer
resource "aws_lb" "main" {
  name               = "sahayak-${var.environment}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids

  drop_invalid_header_fields = true
  enable_deletion_protection = var.environment == "prod"

  tags = {
    Name        = "sahayak-${var.environment}-alb"
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

resource "aws_lb_target_group" "app" {
  name        = "sahayak-${var.environment}-app-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/healthz"
    protocol            = "HTTP"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  deregistration_delay = 30

  tags = {
    Name        = "sahayak-${var.environment}-app-tg"
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

# 6. ACM Certificate & Listeners
resource "aws_acm_certificate" "cert" {
  domain_name       = var.domain_name
  validation_method = "DNS"

  tags = {
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Port 80 HTTP -> Redirect to HTTPS 443
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# Port 443 HTTPS -> Forward to App Target Group
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate.cert.arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

# 7. ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "sahayak-${var.environment}-cluster"

  setting {
    name  = "containerInsights"
    value = var.environment == "prod" ? "enabled" : "disabled"
  }

  tags = {
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

# 8. ECS Task Definition - App
resource "aws_ecs_task_definition" "app" {
  family                   = "sahayak-${var.environment}-app"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = "sahayak-app"
      image     = "${aws_ecr_repository.sahayak.repository_url}:latest"
      essential = true

      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        { name = "ENVIRONMENT", value = var.environment },
        { name = "PORT", value = "8000" },
        { name = "DATABASE_URL", value = "postgresql+asyncpg://sahayak_app@${var.database_endpoint}/${var.database_name}" },
        { name = "REDIS_URL", value = "redis://${var.redis_endpoint}:6379/0" }
      ]

      secrets = [
        {
          name      = "DATABASE_PASSWORD"
          valueFrom = "${aws_secretsmanager_secret.app.arn}:DATABASE_PASSWORD::"
        },
        {
          name      = "GEMINI_API_KEY"
          valueFrom = "${aws_secretsmanager_secret.app.arn}:GEMINI_API_KEY::"
        },
        {
          name      = "GROQ_API_KEY"
          valueFrom = "${aws_secretsmanager_secret.app.arn}:GROQ_API_KEY::"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = "us-east-1"
          "awslogs-stream-prefix" = "app"
        }
      }
    }
  ])
}

# 9. ECS Task Definition - Worker
resource "aws_ecs_task_definition" "worker" {
  family                   = "sahayak-${var.environment}-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = "sahayak-worker"
      image     = "${aws_ecr_repository.sahayak.repository_url}:latest"
      command   = ["uv", "run", "python", "-m", "sahayak.worker"]
      essential = true

      environment = [
        { name = "ENVIRONMENT", value = var.environment },
        { name = "DATABASE_URL", value = "postgresql+asyncpg://sahayak_app@${var.database_endpoint}/${var.database_name}" },
        { name = "REDIS_URL", value = "redis://${var.redis_endpoint}:6379/0" }
      ]

      secrets = [
        {
          name      = "DATABASE_PASSWORD"
          valueFrom = "${aws_secretsmanager_secret.app.arn}:DATABASE_PASSWORD::"
        },
        {
          name      = "GEMINI_API_KEY"
          valueFrom = "${aws_secretsmanager_secret.app.arn}:GEMINI_API_KEY::"
        },
        {
          name      = "GROQ_API_KEY"
          valueFrom = "${aws_secretsmanager_secret.app.arn}:GROQ_API_KEY::"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.worker.name
          "awslogs-region"        = "us-east-1"
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])
}

# 10. ECS Services
resource "aws_ecs_service" "app" {
  name            = "sahayak-${var.environment}-app"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = var.app_task_count
  launch_type     = "FARGATE"

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  network_configuration {
    subnets          = var.private_app_subnet_ids
    security_groups  = [var.ecs_security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "sahayak-app"
    container_port   = 8000
  }

  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [aws_lb_listener.https]
}

resource "aws_ecs_service" "worker" {
  name            = "sahayak-${var.environment}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.worker_task_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_app_subnet_ids
    security_groups  = [var.ecs_security_group_id]
    assign_public_ip = false
  }

  lifecycle {
    ignore_changes = [task_definition]
  }
}

# 11. Autoscaling Policy
resource "aws_appautoscaling_target" "app_scale" {
  max_capacity       = 10
  min_capacity       = var.app_task_count
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.app.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "app_cpu" {
  name               = "sahayak-${var.environment}-cpu-target-tracking"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.app_scale.resource_id
  scalable_dimension = aws_appautoscaling_target.app_scale.scalable_dimension
  service_namespace  = aws_appautoscaling_target.app_scale.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 70.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# 12. Optional Route 53 DNS Record
resource "aws_route53_record" "app" {
  count   = var.route53_zone_id != null ? 1 : 0
  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}
