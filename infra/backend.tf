terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }

  # Remote state per project convention. Populate via -backend-config on init:
  #   terraform init \
  #     -backend-config="bucket=my-pulsecart-tfstate" \
  #     -backend-config="key=pulsecart/terraform.tfstate" \
  #     -backend-config="region=eu-west-1"
  backend "s3" {
    key = "pulsecart/terraform.tfstate"
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "pulsecart"
      ManagedBy   = "terraform"
      Environment = var.environment
    }
  }
}
