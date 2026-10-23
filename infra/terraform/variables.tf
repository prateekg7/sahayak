variable "environment" {
  description = "Target environment (staging, prod)"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "AWS AZs to use"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t4g.micro"
}

variable "db_multi_az" {
  description = "Enable Multi-AZ RDS"
  type        = bool
  default     = false
}

variable "db_master_password" {
  description = "Master password for RDS PostgreSQL"
  type        = string
  sensitive   = true
}

variable "redis_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.t4g.micro"
}

variable "redis_num_clusters" {
  description = "Number of Redis cache nodes"
  type        = number
  default     = 1
}

variable "redis_auth_token" {
  description = "Redis AUTH token (optional)"
  type        = string
  sensitive   = true
  default     = null
}

variable "cognito_domain_prefix" {
  description = "Cognito hosted UI domain prefix"
  type        = string
  default     = "sahayak-auth"
}

variable "alexa_redirect_uris" {
  description = "Allowed Alexa OAuth redirect URIs"
  type        = list(string)
  default = [
    "https://pitangui.amazon.com/api/skill/link/MOCK_SKILL_ID",
    "https://layla.amazon.com/api/skill/link/MOCK_SKILL_ID",
    "https://alexa.amazon.co.jp/api/skill/link/MOCK_SKILL_ID"
  ]
}

variable "domain_name" {
  description = "Public domain name (e.g. api.sahayak.app)"
  type        = string
  default     = "api.sahayak.app"
}

variable "route53_zone_id" {
  description = "Route 53 hosted zone ID for public DNS record"
  type        = string
  default     = null
}
