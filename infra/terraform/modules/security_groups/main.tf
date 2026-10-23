# ALB Security Group (Public HTTPS/HTTP)
resource "aws_security_group" "alb" {
  name        = "sahayak-${var.environment}-alb-sg"
  description = "Controls public inbound traffic to the Application Load Balancer"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP from Internet (redirected to HTTPS)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS from Internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Allow all outbound traffic to ECS tasks"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "sahayak-${var.environment}-alb-sg"
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

# ECS Application Security Group
resource "aws_security_group" "ecs" {
  name        = "sahayak-${var.environment}-ecs-sg"
  description = "Allows inbound traffic only from the ALB to Sahayak MCP container"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Inbound from ALB on container port"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "Allow outbound to RDS, Redis, and Internet via NAT for LLM/Wikipedia"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "sahayak-${var.environment}-ecs-sg"
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

# RDS PostgreSQL Security Group
resource "aws_security_group" "rds" {
  name        = "sahayak-${var.environment}-rds-sg"
  description = "Allows inbound PostgreSQL traffic strictly from ECS tasks"
  vpc_id      = var.vpc_id

  ingress {
    description     = "PostgreSQL from ECS tasks only"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  egress {
    description = "No outbound traffic needed for RDS"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = []
  }

  tags = {
    Name        = "sahayak-${var.environment}-rds-sg"
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

# ElastiCache Redis Security Group
resource "aws_security_group" "redis" {
  name        = "sahayak-${var.environment}-redis-sg"
  description = "Allows inbound Redis traffic strictly from ECS tasks"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Redis from ECS tasks only"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  egress {
    description = "No outbound traffic needed for Redis"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = []
  }

  tags = {
    Name        = "sahayak-${var.environment}-redis-sg"
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}
