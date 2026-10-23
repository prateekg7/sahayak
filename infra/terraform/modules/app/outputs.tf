output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.sahayak.repository_url
}

output "alb_dns_name" {
  description = "Application Load Balancer DNS name"
  value       = aws_lb.main.dns_name
}

output "alb_arn" {
  description = "Application Load Balancer ARN"
  value       = aws_lb.main.arn
}

output "app_target_group_arn" {
  description = "Application Target Group ARN"
  value       = aws_lb_target_group.app.arn
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "app_service_name" {
  description = "ECS app service name"
  value       = aws_ecs_service.app.name
}

output "worker_service_name" {
  description = "ECS worker service name"
  value       = aws_ecs_service.worker.name
}

output "secrets_manager_secret_arn" {
  description = "Secrets Manager secret ARN"
  value       = aws_secretsmanager_secret.app.arn
}

output "public_url" {
  description = "Public service HTTPS URL"
  value       = "https://${var.domain_name}"
}
