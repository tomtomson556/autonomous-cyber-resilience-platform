# IAM Access Strategy

This project separates infrastructure deployment permissions from security validation permissions.

## Purpose

The goal is to keep AWS access aligned with least-privilege principles.

The Python validator should only read and validate the security configuration of explicitly configured S3 backup buckets. It should not have broad account-wide S3 permissions and should not be able to modify infrastructure.

Terraform deployment access should be separated from validator access because Terraform needs infrastructure management permissions, while the validator only needs read-only evidence collection permissions.

## Recommended role separation

Use two separate AWS roles:

* `CyberResilienceTerraformDeployer`

  * Used for Terraform-managed infrastructure deployment.
  * May create, update, or delete lab infrastructure.
  * Should only be used for infrastructure deployment tasks.

* `CyberResilienceS3Validator`

  * Used by the Python S3 security validator.
  * Read-only access.
  * Scoped to explicitly configured S3 backup buckets.
  * Should not have write, delete, or account-wide listing permissions.

## Validator permissions

The validator should not use broad permissions such as:

* `s3:*`
* `s3:ListAllMyBuckets`

The validator only requires read-only permissions for the configured backup buckets.

The current minimum S3 read permissions are documented in:

```text
docs/iam-validator-policy.json
```

These permissions support validation of:

* Bucket versioning
* Server-side encryption
* S3 Object Lock capability
* S3 Block Public Access
* Bucket policy public exposure status
* TLS-only bucket policy enforcement
* Bucket-owner-enforced object ownership

## Credential strategy

Long-lived access keys may be used for local learning and lab testing, but they are not the target architecture.

Preferred future state:

* Human access through IAM Identity Center / SSO with temporary credentials.
* Separate AWS roles for Terraform deployment and security validation.
* GitHub Actions authentication through OIDC instead of stored AWS access keys.
* Trust policies restricted to the specific GitHub repository and branch.
* MFA for human administrative access.
* Root user not used for daily work.

## GitHub Actions OIDC target state

If GitHub Actions later performs live AWS validation or deployment, it should not use stored AWS access keys.

Instead, GitHub Actions should assume a dedicated AWS IAM role through OIDC.

The role trust policy should be restricted to:

* The specific GitHub repository.
* The intended branch or environment.
* The required GitHub Actions workflow context.

This reduces the risk of leaked long-lived credentials and keeps CI/CD access auditable and scoped.

## AccessDenied handling

Some validator checks require specific read permissions, for example:

* `s3:GetBucketPolicy`
* `s3:GetBucketPolicyStatus`
* `s3:GetBucketOwnershipControls`

If these permissions are missing, the validator may report the affected checks as `FAIL`.

This is conservative, but it does not fully distinguish between:

* A bucket that is insecurely configured.
* A bucket that could not be fully evaluated because IAM permissions are missing.

A future improvement should introduce an `UNKNOWN` or `NOT_CHECKED` status for checks that cannot be evaluated due to insufficient IAM permissions.

## Future improvements

Planned IAM-related improvements:

* Replace local long-lived access keys with temporary credentials.
* Add GitHub Actions OIDC-based AWS role assumption.
* Add IAM Access Analyzer evidence for policy validation and least-privilege review.
* Add an `UNKNOWN` report status for checks blocked by insufficient IAM permissions.
* Add separate IAM documentation for Terraform deployment permissions.
* Add environment-specific IAM examples for lab, staging, and production-style deployments.
