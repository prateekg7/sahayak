terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }

  backend "s3" {
    bucket         = "sahayak-terraform-state"
    key            = "sahayak/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "sahayak-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "sahayak"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
