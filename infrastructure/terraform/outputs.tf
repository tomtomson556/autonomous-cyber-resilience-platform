output "bucket_name" {
  description = "Name of the S3 bucket created for the cyber resilience lab."
  value       = aws_s3_bucket.cyber_resilience_lab.bucket
}

output "bucket_arn" {
  description = "ARN of the S3 bucket created for the cyber resilience lab."
  value       = aws_s3_bucket.cyber_resilience_lab.arn
}

output "bucket_region" {
  description = "AWS region where the S3 bucket is deployed."
  value       = aws_s3_bucket.cyber_resilience_lab.region
}
