variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for RDS DB subnet group"
  type        = list(string)
}

variable "security_group_id" {
  description = "Security Group ID for RDS"
  type        = string
}

variable "instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t4g.micro"
}

variable "allocated_storage" {
  description = "Initial allocated storage in GB"
  type        = number
  default     = 20
}

variable "max_allocated_storage" {
  description = "Maximum storage autoscaling limit in GB"
  type        = number
  default     = 100
}

variable "multi_az" {
  description = "Enable Multi-AZ deployment"
  type        = bool
  default     = false
}

variable "database_name" {
  description = "Default database name"
  type        = string
  default     = "sahayak"
}

variable "master_username" {
  description = "Master administrative username"
  type        = string
  default     = "sahayak_admin"
}

variable "master_password" {
  description = "Master administrative password"
  type        = string
  sensitive   = true
}

variable "backup_retention_period" {
  description = "Number of days to retain automated backups (PITR)"
  type        = number
  default     = 7
}

variable "kms_key_arn" {
  description = "Optional KMS key ARN for storage encryption (defaults to AWS managed key if null)"
  type        = string
  default     = null
}
