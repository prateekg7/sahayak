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

output "public_url" {
  description = "Public service HTTPS URL"
  value       = module.app.public_url
}

output "ecr_repository_url" {
  description = "ECR Repository URL"
  value       = module.app.ecr_repository_url
}

output "alb_dns_name" {
  description = "Application Load Balancer DNS name"
  value       = module.app.alb_dns_name
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = module.app.ecs_cluster_name
}

output "app_service_name" {
  description = "ECS app service name"
  value       = module.app.app_service_name
}

output "worker_service_name" {
  description = "ECS worker service name"
  value       = module.app.worker_service_name
}
