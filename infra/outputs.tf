output "raw_stream_name" {
  value = aws_kinesis_stream.raw_clicks.name
}

output "enriched_stream_name" {
  value = aws_kinesis_stream.enriched_clicks.name
}

output "user_features_table" {
  value = aws_dynamodb_table.user_features.name
}

output "product_features_table" {
  value = aws_dynamodb_table.product_features.name
}

output "enricher_function_arn" {
  value = aws_lambda_function.enricher.arn
}

output "redshift_streaming_role_arn" {
  value       = aws_iam_role.redshift_streaming.arn
  description = "Passed into redshift_streaming.sql when running it against the workgroup."
}

output "redshift_workgroup" {
  value = aws_redshiftserverless_workgroup.pulsecart.workgroup_name
}

output "redshift_endpoint" {
  description = "Redshift Serverless workgroup endpoint (host:port/dbname)."
  value       = aws_redshiftserverless_workgroup.pulsecart.endpoint[0].address
}
