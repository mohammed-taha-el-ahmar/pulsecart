resource "aws_kinesis_stream" "raw_clicks" {
  name             = var.kinesis_raw_stream
  retention_period = 24

  stream_mode_details {
    stream_mode = "ON_DEMAND"
  }
}

resource "aws_kinesis_stream" "enriched_clicks" {
  name             = var.kinesis_enriched_stream
  retention_period = 24

  stream_mode_details {
    stream_mode = "ON_DEMAND"
  }
}
