# ==============================================================================
# CloudWatch Metric Alarms & Alert Routing (T4.4)
# ==============================================================================

resource "aws_sns_topic" "alerts" {
  name = "sahayak-${var.environment}-alerts"

  tags = {
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

# 1. High Error Rate Alarm (Error rate > 1% over 5 minutes)
resource "aws_cloudwatch_metric_alarm" "high_error_rate" {
  alarm_name          = "sahayak-${var.environment}-high-error-rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 300 # 5 minutes
  statistic           = "Sum"
  threshold           = 1.0 # > 1% of nominal request volume
  alarm_description   = "Triggered when 5XX error rate exceeds threshold over 5 minutes"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  dimensions = {
    LoadBalancer = var.alb_arn
    TargetGroup  = var.app_target_group_arn
  }
}

# 2. P95 Latency Over Budget Alarm (> 800ms over 5 minutes)
resource "aws_cloudwatch_metric_alarm" "high_latency_p95" {
  alarm_name          = "sahayak-${var.environment}-high-latency-p95"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "TargetResponseTime"
  namespace           = "AWS/ApplicationELB"
  period              = 300
  extended_statistic  = "p95"
  threshold           = 0.8 # 800ms
  alarm_description   = "Triggered when p95 target response time exceeds voice latency budget (800ms)"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  dimensions = {
    LoadBalancer = var.alb_arn
    TargetGroup  = var.app_target_group_arn
  }
}

# 3. RDS High Database Connections (> 80% capacity)
resource "aws_cloudwatch_metric_alarm" "rds_high_connections" {
  alarm_name          = "sahayak-${var.environment}-rds-high-connections"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "RDS database connection pool exceeds 80% of max capacity"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    DBInstanceIdentifier = var.db_instance_id
  }
}

# 4. Redis High Memory Utilization (> 80%)
resource "aws_cloudwatch_metric_alarm" "redis_high_memory" {
  alarm_name          = "sahayak-${var.environment}-redis-high-memory"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "DatabaseMemoryUsagePercentage"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Average"
  threshold           = 80.0
  alarm_description   = "ElastiCache Redis memory utilization exceeds 80%"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# 5. LLM Fallback Spike Alarm (Custom metric from Prometheus/CloudWatch Agent)
resource "aws_cloudwatch_metric_alarm" "llm_fallback_spike" {
  alarm_name          = "sahayak-${var.environment}-llm-fallback-spike"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "sahayak_llm_fallbacks_total"
  namespace           = "Sahayak/Application"
  period              = 60
  statistic           = "Sum"
  threshold           = 5.0 # More than 5 fallbacks per minute
  alarm_description   = "Spike in LLM provider fallbacks or circuit breaker trips"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# 6. Daily LLM Budget Exhaustion Alarm
resource "aws_cloudwatch_metric_alarm" "llm_budget_exhaustion" {
  alarm_name          = "sahayak-${var.environment}-llm-budget-exhaustion"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "sahayak_llm_budget_exhaustion_count"
  namespace           = "Sahayak/Application"
  period              = 300
  statistic           = "Sum"
  threshold           = 0.0 # Any budget exhaustion event
  alarm_description   = "Daily token or monetary budget reached for one or more LLM providers"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}
