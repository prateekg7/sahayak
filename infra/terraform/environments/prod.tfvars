environment           = "prod"
aws_region            = "us-east-1"
vpc_cidr              = "10.20.0.0/16"
availability_zones    = ["us-east-1a", "us-east-1b"]

db_instance_class     = "db.m6g.large"
db_multi_az           = true
db_master_password    = "ProdInjectFromSecretsManagerOrKMS!"

redis_node_type       = "cache.m6g.large"
redis_num_clusters    = 2

cognito_domain_prefix = "sahayak-prod-auth"
