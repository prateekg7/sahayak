terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

# 1. Cognito User Pool
resource "aws_cognito_user_pool" "pool" {
  name = "sahayak-${var.environment}-user-pool"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
    require_uppercase = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  admin_create_user_config {
    allow_admin_create_user_only = false
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    mutable             = false
    required            = true
  }

  tags = {
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

# 2. Resource Server (Audience = sahayak-api, Custom Scopes = academics.read/write)
resource "aws_cognito_resource_server" "resource_server" {
  identifier   = var.resource_server_identifier
  name         = "Sahayak MCP Resource Server"
  user_pool_id = aws_cognito_user_pool.pool.id

  scope {
    scope_name        = "academics.read"
    scope_description = "Read access to academics, quizzes, and progress"
  }

  scope {
    scope_name        = "academics.write"
    scope_description = "Write access to answer quizzes and modify study plans"
  }
}

# 3. User Pool Domain (Hosted UI for OAuth login/consent)
resource "aws_cognito_user_pool_domain" "domain" {
  domain       = var.cognito_domain_prefix
  user_pool_id = aws_cognito_user_pool.pool.id
}

# 4. App Client for Alexa+ (Authorization Code Grant with PKCE, Secret optional/included)
resource "aws_cognito_user_pool_client" "alexa_client" {
  name         = "sahayak-alexa-plus-${var.environment}"
  user_pool_id = aws_cognito_user_pool.pool.id

  generate_secret = true

  allowed_oauth_flows                  = ["code"]
  allowed_oauth_flows_user_pool_client = true

  allowed_oauth_scopes = [
    "openid",
    "email",
    "profile",
    "${aws_cognito_resource_server.resource_server.identifier}/academics.read",
    "${aws_cognito_resource_server.resource_server.identifier}/academics.write",
  ]

  callback_urls = var.alexa_redirect_uris
  logout_urls   = var.alexa_redirect_uris

  supported_identity_providers = ["COGNITO"]

  prevent_user_existence_errors = "ENABLED"
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  depends_on = [
    aws_cognito_resource_server.resource_server
  ]
}
