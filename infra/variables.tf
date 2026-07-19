variable "aws_region" {
  description = "AWS region."
  type        = string
  default     = "eu-west-1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)."
  type        = string
  default     = "dev"
}

variable "kinesis_raw_stream" {
  description = "Kinesis stream name for raw click events."
  type        = string
  default     = "pulsecart-raw-clicks"
}

variable "kinesis_enriched_stream" {
  description = "Kinesis stream name for enriched events."
  type        = string
  default     = "pulsecart-enriched-clicks"
}

variable "kinesis_shard_count" {
  description = "Shards for the streams (on-demand keeps costs down for dev)."
  type        = number
  default     = 1
}

variable "dynamodb_user_table" {
  description = "DynamoDB table for user features."
  type        = string
  default     = "pulsecart-user-features"
}

variable "dynamodb_product_table" {
  description = "DynamoDB table for product features."
  type        = string
  default     = "pulsecart-product-features"
}

variable "sagemaker_endpoint_name" {
  description = "SageMaker endpoint that hosts the ranker."
  type        = string
  default     = "pulsecart-ranker-endpoint"
}

variable "lambda_package" {
  description = "Path to the enricher deployment zip (built by CI)."
  type        = string
  default     = "../artifacts/enricher.zip"
}

variable "redshift_workgroup" {
  description = "Redshift Serverless workgroup name."
  type        = string
  default     = "pulsecart"
}

variable "redshift_namespace" {
  description = "Redshift Serverless namespace name."
  type        = string
  default     = "pulsecart"
}

variable "redshift_admin_username" {
  description = "Redshift admin username."
  type        = string
  default     = "pulsecart_admin"
}

variable "redshift_admin_password" {
  description = "Redshift admin password. Must contain at least one uppercase letter, one lowercase letter, and one digit."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("[A-Z]", var.redshift_admin_password)) && can(regex("[a-z]", var.redshift_admin_password)) && can(regex("[0-9]", var.redshift_admin_password))
    error_message = "Password must contain at least one uppercase letter, one lowercase letter, and one digit."
  }
}
