# 1. VPC & Networking
module "vpc" {
  source = "./modules/vpc"

  environment        = var.environment
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
}

# 2. Security Groups
module "security_groups" {
  source = "./modules/security_groups"

  environment = var.environment
  vpc_id      = module.vpc.vpc_id
}

# 3. RDS PostgreSQL Database
module "database" {
  source = "./modules/database"

  environment       = var.environment
  subnet_ids        = module.vpc.private_db_subnet_ids
  security_group_id = module.security_groups.rds_security_group_id

  instance_class    = var.db_instance_class
  multi_az          = var.db_multi_az
  master_password   = var.db_master_password
}

# 4. ElastiCache Redis
module "cache" {
  source = "./modules/cache"

  environment        = var.environment
  subnet_ids         = module.vpc.private_db_subnet_ids
  security_group_id  = module.security_groups.redis_security_group_id

  node_type          = var.redis_node_type
  num_cache_clusters = var.redis_num_clusters
  auth_token         = var.redis_auth_token
}

# 5. Cognito Identity Provider (T1.7)
module "idp" {
  source = "./idp"

  environment                 = var.environment
  resource_server_identifier  = "sahayak-api"
  cognito_domain_prefix       = "${var.cognito_domain_prefix}-${var.environment}"
  alexa_redirect_uris         = var.alexa_redirect_uris
}

# 6. ECS Application Platform, ALB, TLS, DNS (T4.2)
module "app" {
  source = "./modules/app"

  environment            = var.environment
  vpc_id                 = module.vpc.vpc_id
  public_subnet_ids      = module.vpc.public_subnet_ids
  private_app_subnet_ids = module.vpc.private_app_subnet_ids
  alb_security_group_id  = module.security_groups.alb_security_group_id
  ecs_security_group_id  = module.security_groups.ecs_security_group_id

  domain_name            = var.domain_name
  route53_zone_id        = var.route53_zone_id
  database_endpoint      = module.database.db_endpoint
  database_name          = module.database.db_name
  redis_endpoint         = module.cache.primary_endpoint_address
}
