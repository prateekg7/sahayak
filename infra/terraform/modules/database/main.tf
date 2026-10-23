resource "aws_db_subnet_group" "rds" {
  name        = "sahayak-${var.environment}-db-subnet-group"
  description = "Database subnet group for Sahayak RDS PostgreSQL"
  subnet_ids  = var.subnet_ids

  tags = {
    Name        = "sahayak-${var.environment}-db-subnet-group"
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

resource "aws_db_parameter_group" "pg16" {
  name        = "sahayak-${var.environment}-pg16-params"
  family      = "postgres16"
  description = "PostgreSQL 16 parameter group with SSL enforcement and query logging"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "200" # Log queries taking more than 200ms
  }

  parameter {
    name  = "log_connections"
    value = "1"
  }

  parameter {
    name  = "log_disconnections"
    value = "1"
  }

  tags = {
    Name        = "sahayak-${var.environment}-pg16-params"
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

resource "aws_db_instance" "postgres" {
  identifier                  = "sahayak-${var.environment}-postgres"
  engine                      = "postgres"
  engine_version              = "16.3"
  instance_class              = var.instance_class
  allocated_storage           = var.allocated_storage
  max_allocated_storage       = var.max_allocated_storage
  storage_type                = "gp3"
  storage_encrypted           = true
  kms_key_id                  = var.kms_key_arn

  db_name                     = var.database_name
  username                    = var.master_username
  password                    = var.master_password
  port                        = 5432

  multi_az                    = var.multi_az
  db_subnet_group_name        = aws_db_subnet_group.rds.name
  vpc_security_group_ids      = [var.security_group_id]
  parameter_group_name        = aws_db_parameter_group.pg16.name
  publicly_accessible         = false

  backup_retention_period     = var.backup_retention_period
  backup_window               = "03:00-04:00"
  maintenance_window          = "Sun:04:30-Sun:05:30"
  auto_minor_version_upgrade  = true
  allow_major_version_upgrade = false
  deletion_protection         = var.environment == "prod"
  skip_final_snapshot         = var.environment != "prod"
  final_snapshot_identifier   = var.environment == "prod" ? "sahayak-prod-final-${formatdate("YYYY-MM-DD-hh-mm", timestamp())}" : null

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  tags = {
    Name        = "sahayak-${var.environment}-postgres"
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}
