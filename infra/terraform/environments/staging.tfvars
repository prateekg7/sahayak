environment           = "staging"
aws_region            = "us-east-1"
vpc_cidr              = "10.10.0.0/16"
availability_zones    = ["us-east-1a", "us-east-1b"]

db_instance_class     = "db.t4g.micro"
db_multi_az           = false
db_master_password    = "StagingChangeMeInSecretsManager123!"

redis_node_type       = "cache.t4g.micro"
redis_num_clusters    = 1

cognito_domain_prefix = "sahayak-staging-auth"
