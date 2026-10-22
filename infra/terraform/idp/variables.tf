variable "aws_region" {
  description = "AWS region for Cognito User Pool"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (staging, prod)"
  type        = string
  default     = "staging"
}

variable "cognito_domain_prefix" {
  description = "Globally unique subdomain prefix for the Cognito Hosted UI"
  type        = string
  default     = "sahayak-auth-staging"
}

variable "resource_server_identifier" {
  description = "Audience identifier for Sahayak MCP tokens"
  type        = string
  default     = "sahayak-api"
}

variable "alexa_redirect_uris" {
  description = "Amazon Alexa account linking callback URLs"
  type        = list(string)
  default = [
    "https://pitangui.amazon.com/api/flutter/skill-linking/callback",
    "https://layla.amazon.com/api/flutter/skill-linking/callback",
    "https://alexa.amazon.co.jp/api/flutter/skill-linking/callback",
    "https://oauth.developer.amazon.com/response_types/token/cb",
  ]
}
