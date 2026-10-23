resource "aws_elasticache_subnet_group" "redis" {
  name        = "sahayak-${var.environment}-redis-subnet-group"
  description = "Subnet group for Sahayak ElastiCache Redis"
  subnet_ids  = var.subnet_ids

  tags = {
    Name        = "sahayak-${var.environment}-redis-subnet-group"
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

resource "aws_elasticache_parameter_group" "redis7" {
  name        = "sahayak-${var.environment}-redis7-params"
  family      = "redis7"
  description = "Redis 7 parameter group with LRU memory eviction"

  parameter {
    name  = "maxmemory-policy"
    value = "volatile-lru"
  }

  tags = {
    Name        = "sahayak-${var.environment}-redis7-params"
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = "sahayak-${var.environment}-redis"
  description                = "Redis cluster for Sahayak rate-limiting, caching, and background queues"
  node_type                  = var.node_type
  num_cache_clusters         = var.num_cache_clusters
  port                       = 6379
  parameter_group_name       = aws_elasticache_parameter_group.redis7.name
  subnet_group_name          = aws_elasticache_subnet_group.redis.name
  security_group_ids         = [var.security_group_id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = var.auth_token

  automatic_failover_enabled = var.num_cache_clusters > 1
  multi_az_enabled           = var.num_cache_clusters > 1

  maintenance_window         = "sun:06:00-sun:07:00"
  snapshot_retention_limit   = var.environment == "prod" ? 7 : 0
  snapshot_window            = var.environment == "prod" ? "02:00-03:00" : null

  tags = {
    Name        = "sahayak-${var.environment}-redis"
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}
