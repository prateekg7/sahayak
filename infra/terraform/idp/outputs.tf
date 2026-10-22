output "user_pool_id" {
  description = "ID of the created Cognito User Pool"
  value       = aws_cognito_user_pool.pool.id
}

output "user_pool_arn" {
  description = "ARN of the Cognito User Pool"
  value       = aws_cognito_user_pool.pool.arn
}

output "user_pool_client_id" {
  description = "Client ID for Alexa+ add-on configuration"
  value       = aws_cognito_user_pool_client.alexa_client.id
}

output "user_pool_client_secret" {
  description = "Client Secret for Alexa+ add-on configuration"
  value       = aws_cognito_user_pool_client.alexa_client.client_secret
  sensitive   = true
}

output "issuer_url" {
  description = "JWT Issuer URL for Sahayak Settings (OIDC_ISSUER)"
  value       = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.pool.id}"
}

output "jwks_url" {
  description = "JWKS URL for Sahayak Settings (OIDC_JWKS_URL)"
  value       = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.pool.id}/.well-known/jwks.json"
}

output "authorization_endpoint" {
  description = "OAuth 2.1 Authorization URI for Alexa+ add-on"
  value       = "https://${aws_cognito_user_pool_domain.domain.domain}.auth.${var.aws_region}.amazoncognito.com/oauth2/authorize"
}

output "token_endpoint" {
  description = "OAuth 2.1 Access Token URI for Alexa+ add-on"
  value       = "https://${aws_cognito_user_pool_domain.domain.domain}.auth.${var.aws_region}.amazoncognito.com/oauth2/token"
}

output "resource_server_identifier" {
  description = "Audience string for Sahayak Settings (OIDC_AUDIENCE)"
  value       = var.resource_server_identifier
}
