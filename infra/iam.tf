# ------------------------------------------------------------------------------
# Lambda enricher execution role
# ------------------------------------------------------------------------------
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "enricher" {
  name               = "pulsecart-enricher-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "enricher_basic" {
  role       = aws_iam_role.enricher.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "enricher_inline" {
  statement {
    actions = [
      "kinesis:DescribeStream",
      "kinesis:DescribeStreamSummary",
      "kinesis:GetRecords",
      "kinesis:GetShardIterator",
      "kinesis:ListShards",
      "kinesis:SubscribeToShard",
    ]
    resources = [aws_kinesis_stream.raw_clicks.arn]
  }
  statement {
    actions   = ["kinesis:PutRecord", "kinesis:PutRecords"]
    resources = [aws_kinesis_stream.enriched_clicks.arn]
  }
  statement {
    actions = ["dynamodb:GetItem", "dynamodb:BatchGetItem"]
    resources = [
      aws_dynamodb_table.user_features.arn,
      aws_dynamodb_table.product_features.arn,
    ]
  }
  statement {
    actions   = ["sagemaker:InvokeEndpoint"]
    resources = ["arn:aws:sagemaker:${var.aws_region}:*:endpoint/${var.sagemaker_endpoint_name}"]
  }
  statement {
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "enricher_inline" {
  name   = "pulsecart-enricher-inline"
  role   = aws_iam_role.enricher.id
  policy = data.aws_iam_policy_document.enricher_inline.json
}

# ------------------------------------------------------------------------------
# Redshift streaming ingestion role
# ------------------------------------------------------------------------------
data "aws_iam_policy_document" "redshift_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["redshift.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "redshift_streaming" {
  name               = "pulsecart-redshift-streaming"
  assume_role_policy = data.aws_iam_policy_document.redshift_assume.json
}

data "aws_iam_policy_document" "redshift_streaming_inline" {
  statement {
    actions = [
      "kinesis:DescribeStream",
      "kinesis:DescribeStreamSummary",
      "kinesis:GetRecords",
      "kinesis:GetShardIterator",
      "kinesis:ListShards",
      "kinesis:ListStreams",
      "kinesis:SubscribeToShard",
    ]
    resources = [aws_kinesis_stream.enriched_clicks.arn]
  }
}

resource "aws_iam_role_policy" "redshift_streaming_inline" {
  name   = "pulsecart-redshift-streaming-inline"
  role   = aws_iam_role.redshift_streaming.id
  policy = data.aws_iam_policy_document.redshift_streaming_inline.json
}
