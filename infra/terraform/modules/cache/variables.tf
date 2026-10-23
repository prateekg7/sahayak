variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for ElastiCache subnet group"
  type        = list(string)
}

variable "security_group_id" {
  description = "Security Group ID for Redis"
  type        = string
}

variable "node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.t4g.micro"
}

variable "num_cache_clusters" {
  description = "Number of cache clusters (1 for staging single-node, 2+ for prod replication group)"
  type        = number
  default     = 1
}

variable "auth_token" {
  description = "Redis AUTH token (optional, requires transit_encryption_enabled)"
  type        = string
  sensitive   = true
  default     = null
}
