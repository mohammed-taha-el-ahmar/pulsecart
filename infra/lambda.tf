resource "aws_s3_bucket" "lambda_artifacts" {
  bucket_prefix = "pulsecart-lambda-artifacts-"
  force_destroy = true
}

resource "aws_s3_object" "enricher_zip" {
  bucket = aws_s3_bucket.lambda_artifacts.id
  key    = "enricher.zip"
  source = var.lambda_package
  etag   = fileexists(var.lambda_package) ? filemd5(var.lambda_package) : null
}

resource "aws_lambda_function" "enricher" {
  function_name = "pulsecart-enricher"
  role          = aws_iam_role.enricher.arn
  runtime       = "python3.11"
  handler       = "pulsecart.enricher.handler.lambda_handler"
  s3_bucket     = aws_s3_bucket.lambda_artifacts.id
  s3_key        = aws_s3_object.enricher_zip.key
  timeout       = 60
  memory_size   = 512

  environment {
    variables = {
      PULSECART_MODE                    = "aws"
      PULSECART_AWS_REGION              = var.aws_region
      PULSECART_KINESIS_RAW_STREAM      = aws_kinesis_stream.raw_clicks.name
      PULSECART_KINESIS_ENRICHED_STREAM = aws_kinesis_stream.enriched_clicks.name
      PULSECART_DYNAMODB_USER_TABLE     = aws_dynamodb_table.user_features.name
      PULSECART_DYNAMODB_PRODUCT_TABLE  = aws_dynamodb_table.product_features.name
      PULSECART_SAGEMAKER_ENDPOINT_NAME = "none"
      PULSECART_MODEL_PATH              = "/var/task/artifacts/ranker.joblib"
      LD_LIBRARY_PATH                   = "/var/task/lib:/var/task/scikit_learn.libs:/var/lang/lib:/lib64:/usr/lib64"
    }
  }

  # source_code_hash forces redeploy when the zip changes.
  source_code_hash = filebase64sha256(var.lambda_package)
}

resource "aws_lambda_event_source_mapping" "enricher_from_raw" {
  event_source_arn                   = aws_kinesis_stream.raw_clicks.arn
  function_name                      = aws_lambda_function.enricher.arn
  starting_position                  = "LATEST"
  batch_size                         = 50
  maximum_batching_window_in_seconds = 2
  function_response_types            = ["ReportBatchItemFailures"]
}

resource "aws_cloudwatch_log_group" "enricher" {
  name              = "/aws/lambda/${aws_lambda_function.enricher.function_name}"
  retention_in_days = 14
}
