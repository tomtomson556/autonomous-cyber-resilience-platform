# GitHub Actions OIDC Validator Role

This document describes the AWS IAM role used by the manual GitHub Actions S3 security validation workflow.

The role is intended for read-only validation of the Terraform-managed S3 lab bucket:

```text
cyber-resilience-objectlock-lab-tom-2026
```

It should not be used for Terraform deployment and should not include S3 write, delete, or account-wide listing permissions.

## Trust Policy

The trust policy allows GitHub Actions from this repository's `main` branch to assume the role through OpenID Connect.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GitHubActionsOIDCTrust",
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::061650022648:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:tomtomson556/autonomous-cyber-resilience-platform:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

## Permission Policy

The permission policy is scoped to read-only bucket configuration checks required by the S3 security validator.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3BucketSecurityValidation",
      "Effect": "Allow",
      "Action": [
        "s3:GetBucketVersioning",
        "s3:GetEncryptionConfiguration",
        "s3:GetBucketObjectLockConfiguration",
        "s3:GetBucketPublicAccessBlock",
        "s3:GetBucketPolicy",
        "s3:GetBucketPolicyStatus",
        "s3:GetBucketOwnershipControls",
        "s3:GetBucketLocation"
      ],
      "Resource": "arn:aws:s3:::cyber-resilience-objectlock-lab-tom-2026"
    }
  ]
}
```

## Operational Notes

- Use this role only from the manual `AWS S3 Security Validation` workflow.
- Keep Terraform deployment permissions in a separate role.
- Do not attach `AmazonS3FullAccess`, `s3:*`, `Put*`, or `Delete*` permissions to this role.
- Consider migrating the trust condition to a protected GitHub Environment if validation should require approval.
