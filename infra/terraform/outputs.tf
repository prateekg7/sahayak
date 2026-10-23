output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = module.vpc.public_subnet_ids
}

output "private_app_subnet_ids" {
  description = "Private application subnet IDs"
  value       = module.vpc.private_app_subnet_ids
}

output "database_endpoint" {
  description = "PostgreSQL endpoint"
  value       = module.database.db_endpoint
}

output "database_name" {
  description = "Database name"
  value       = module.database.db_name
}

output "redis_primary_endpoint" {
  description = "Redis primary endpoint"
  value       = module.cache.primary_endpoint_address
}

output "alb_security_group_id" {
  description = "ALB security group ID"
  value       = module.security_groups.alb_security_group_id
}

output "ecs_security_group_id" {
  description = "ECS security group ID"
  value       = module.security_groups.ecs_security_group_id
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = module.idp.cognito_user_pool_id
}

output "cognito_user_pool_client_id" {
  description = "Cognito Alexa Client ID"
  value       = module.idp.cognito_user_pool_client_id
}

output "cognito_issuer_url" {
  description = "Cognito Issuer URL"
  value       = module.idp.cognito_issuer_url
}
