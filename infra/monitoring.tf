# Enricher error-rate alarm — fires when >5 errors in a 5-min window. Keeps the
# observability story concrete: "we alert on enricher failures, not just log them".
resource "aws_cloudwatch_metric_alarm" "enricher_errors" {
  alarm_name          = "pulsecart-enricher-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"
  alarm_description   = "Enricher Lambda error rate above threshold."
  dimensions = {
    FunctionName = aws_lambda_function.enricher.function_name
  }
}

# Iterator age alarm — Kinesis consumer lag. Above ~60s ⇒ we're falling behind.
resource "aws_cloudwatch_metric_alarm" "enricher_iterator_age" {
  alarm_name          = "pulsecart-enricher-iterator-age"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "IteratorAge"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Maximum"
  threshold           = 60000
  treat_missing_data  = "notBreaching"
  alarm_description   = "Enricher is falling behind the raw stream (>60s)."
  dimensions = {
    FunctionName = aws_lambda_function.enricher.function_name
  }
}
