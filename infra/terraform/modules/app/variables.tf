variable "environment" {
  description = "Target deployment environment (staging, prod)"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for the ALB"
  type        = list(string)
}

variable "private_app_subnet_ids" {
  description = "Private subnet IDs for ECS tasks"
  type        = list(string)
}

variable "alb_security_group_id" {
  description = "Security Group ID for ALB"
  type        = string
}

variable "ecs_security_group_id" {
  description = "Security Group ID for ECS tasks"
  type        = string
}

variable "domain_name" {
  description = "Public domain name (e.g., api.sahayak.app)"
  type        = string
  default     = "api.sahayak.app"
}

variable "route53_zone_id" {
  description = "Optional Route 53 hosted zone ID for DNS records"
  type        = string
  default     = null
}

variable "app_task_count" {
  description = "Desired number of app container instances (>= 2 for high availability)"
  type        = number
  default     = 2
}

variable "worker_task_count" {
  description = "Desired number of background worker container instances"
  type        = number
  default     = 1
}

variable "database_endpoint" {
  description = "PostgreSQL endpoint"
  type        = string
}

variable "database_name" {
  description = "Database name"
  type        = string
  default     = "sahayak"
}

variable "redis_endpoint" {
  description = "Redis primary endpoint"
  type        = string
}
