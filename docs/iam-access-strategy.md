# IAM Access Strategy

This project separates infrastructure deployment permissions from security validation permissions.

## Purpose

The goal is to keep AWS access aligned with least-privilege principles.

The Python validator should only read and validate the security configuration of explicitly configured S3 backup buckets. It should not have broad account-wide S3 permissions and should not be able to modify infrastructure.

Terraform deployment access should be separated from validator access because Terraform needs infrastructure management permissions, while the validator only needs read-only evidence collection permissions.

## Identity and role separation

Validation and infrastructure deployment use separate AWS identities with
least-privilege permissions:

* Local S3 validator identity

  * Accessed through the AWS default credential provider chain.
  * Currently documented with the local AWS profile `cyber-resilience-bot`.
  * Has read-only permissions for security validation.

* Local Terraform deployment identity

  * Uses a separate AWS profile or identity.
  * May create, update, or delete lab infrastructure.
  * Must not be used for routine security validation.
  * OIDC-based Terraform deployment is not currently implemented.

* `GitHubActionsS3ValidatorRole`

  * Assumed by the GitHub Actions S3 security validation workflow through OIDC.
  * Read-only access.
  * Scoped to the `cyber-resilience-objectlock-lab-tom-2026` S3 bucket.
  * Does not grant write, delete, or account-wide listing permissions.

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

## Current credential strategy

Long-lived access keys may be used for local learning and lab testing, but they are not the target architecture.

The manual GitHub Actions S3 security validation workflow currently:

* Authenticates to AWS through GitHub Actions OIDC.
* Assumes the dedicated `GitHubActionsS3ValidatorRole`.
* Uses short-lived AWS credentials instead of stored AWS access keys.
* Restricts role assumption to this repository's `main` branch.
* Uses a read-only permission policy scoped to the
  `cyber-resilience-objectlock-lab-tom-2026` S3 bucket.

Human administrative access should use IAM Identity Center / SSO with temporary
credentials where available. MFA should protect human administrative access,
and the root user should not be used for daily work.

## Implemented GitHub Actions OIDC validation

GitHub Actions performs live, read-only S3 security validation by assuming the
dedicated `GitHubActionsS3ValidatorRole` through OIDC.

The implemented trust policy is restricted to:

* The specific GitHub repository.
* The `main` branch.
* The AWS Security Token Service audience.

The role permission policy is restricted to the read-only S3 configuration
actions required by the validator and the
`cyber-resilience-objectlock-lab-tom-2026` bucket. It does not grant S3 write,
delete, or account-wide listing permissions.

The detailed trust and permission policies are documented in:

```text
docs/github-oidc-validator-role.md
```

This implementation reduces the risk of leaked long-lived credentials and
keeps cloud validation access auditable and scoped.

## Terraform deployment access

Terraform deployment through GitHub Actions OIDC is not currently implemented.
Terraform deployment permissions must remain separate from the read-only
validator role. The `GitHubActionsS3ValidatorRole` must never be extended with
infrastructure deployment, S3 write, or S3 delete permissions.

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
* Add a separate OIDC-based Terraform deployment workflow and deployment role.
* Add IAM Access Analyzer evidence for policy validation and least-privilege review.
* Add an `UNKNOWN` report status for checks blocked by insufficient IAM permissions.
* Add separate IAM documentation for Terraform deployment permissions.
* Add environment-specific IAM examples for lab, staging, and production-style deployments.
