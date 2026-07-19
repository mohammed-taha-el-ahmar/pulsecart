resource "aws_redshiftserverless_namespace" "pulsecart" {
  namespace_name       = var.redshift_namespace
  admin_username       = var.redshift_admin_username
  admin_user_password  = var.redshift_admin_password
  db_name              = "pulsecart"
  iam_roles            = [aws_iam_role.redshift_streaming.arn]
  default_iam_role_arn = aws_iam_role.redshift_streaming.arn
}

resource "aws_redshiftserverless_workgroup" "pulsecart" {
  namespace_name = aws_redshiftserverless_namespace.pulsecart.namespace_name
  workgroup_name = var.redshift_workgroup
  base_capacity  = 8

  publicly_accessible = true
}
