# Terraform Remote State Hardening Runbook

## Purpose and safety boundary

This runbook describes a reviewed path from local Terraform state toward a
dedicated Amazon S3 remote backend with native S3 lockfile locking. It is
documentation only. It does not perform or authorize a backend migration,
change live infrastructure, or establish that any current local state file is
complete, authoritative, or safe.

All commands in the migration checklist are **manual operator steps**. They
must be run only after explicit approval, with an identified authoritative
state source, an independently verified backup, and exclusive control of
Terraform activity.

Use the
[Terraform S3 remote state migration specification](terraform-s3-remote-state-migration-spec.md)
to record unresolved decisions, approvals, responsibilities, and future
Go/No-Go gates before any migration is authorized.

Do not print, parse, commit, or expose Terraform state while following this
runbook. State can contain sensitive values even when the corresponding
Terraform outputs are marked sensitive.

## Current project observations

- The main Terraform root module manages the S3 lab/application bucket. The
  remote-state bucket must be a different bucket with an independent lifecycle.
- The checked-in Terraform configuration contains no backend block.
- No checked-in Terraform workspace configuration was found. This project must
  use only the default workspace unless a separate workspace design is reviewed
  and approved before use. This does not prove that workspaces have never been
  used locally.
- The Terraform configuration requires Terraform `>= 1.10.0`. Native S3
  lockfile locking with `use_lockfile` was introduced as experimental in
  Terraform `1.10`; all operators, CI jobs, and other automation must therefore
  use Terraform `>= 1.10.0` before this design is adopted.
- The existing `.gitignore` excludes `.terraform/`, `*.tfstate`,
  `*.tfstate.backup`, `*.tfvars`, `.env`, and `reports/`. ZIP archives are not
  globally ignored. No ignore rule was changed because globally excluding ZIP
  files without an established artifact pattern could hide intentional
  repository content.

## Target architecture

Use a dedicated S3 bucket only for Terraform state:

- Keep it separate from the existing lab/application bucket.
- Do not manage it from the main application Terraform stack whose state it
  stores.
- Prefer an isolated bootstrap process, such as a small CloudFormation stack, a
  separately approved AWS CLI procedure, or a separate administrative
  Terraform root module with its own independently protected state.
- Place it in `eu-central-1`.
- Use a globally unique placeholder-based naming convention, such as
  `<account-id>-eu-central-1-acrp-tfstate` or
  `acrp-terraform-state-eu-central-1-<unique-suffix>`.
- Enable S3 Versioning before writing state.
- Enable SSE-KMS with a customer-managed KMS key and key rotation after its
  additional key-policy, availability, and cost requirements are reviewed.
- Consider an S3 Bucket Key when using SSE-KMS to reduce KMS request traffic
  and cost. Review the changed encryption context before enabling it.
- Fully enable S3 Block Public Access.
- Set S3 Object Ownership to `BucketOwnerEnforced` so ACLs are disabled.
- Require TLS through a bucket policy using `aws:SecureTransport`.
- Enable native Terraform S3 lockfile locking with `use_lockfile = true`.
- Do not introduce new DynamoDB locking. Current HashiCorp documentation marks
  DynamoDB-based S3 backend locking as deprecated.
- Audit backend access. Consider CloudTrail S3 data events for the narrowly
  scoped state prefix because normal CloudTrail event history does not include
  S3 object-level data events by default.

The backend resources and their administrative recovery role should have a
different lifecycle and permission boundary from the infrastructure managed by
the main Terraform root module. A separate administrative AWS account provides
stronger isolation where the operating model supports it.

## Backend configuration example

The following is a non-executing example for later review. It must remain a
documentation example until backend resources, permissions, authoritative
state, backups, and the migration procedure have been independently reviewed.
Use placeholders only; do not commit credentials or sensitive backend
configuration.

```hcl
terraform {
  backend "s3" {
    bucket       = "<globally-unique-state-bucket>"
    key          = "autonomous-cyber-resilience-platform/lab/terraform.tfstate"
    region       = "eu-central-1"
    encrypt      = true
    use_lockfile = true
  }
}
```

The final approved backend configuration must additionally refer to the full
customer-managed KMS key ARN, not only an alias. This readiness example uses a
placeholder:

```hcl
kms_key_id = "<customer-managed-kms-key-arn>"
```

Use short-lived credentials from the AWS credential provider chain. Do not put
credentials or other secrets in the backend block or `-backend-config`
arguments; HashiCorp warns that backend configuration values can be persisted
in `.terraform` metadata and plan files.

## Consistency, locking, and retention

### Strong consistency is not state locking

Amazon S3 provides strong read-after-write consistency and atomic updates to a
single key. This ensures that a read after a completed write observes the new
object, but it does not coordinate competing Terraform processes.

AWS documents that S3 does not provide object locking for concurrent writers
and uses last-writer-wins behavior for simultaneous writes to one key.
Terraform locking instead prevents two operators or automation jobs from
changing the same state at the same time. Strong consistency makes reads and
writes predictable; `use_lockfile = true` provides the required coordination.

### Object Lock is not state locking

S3 Object Lock provides WORM retention or legal holds for individual object
versions. It protects retained versions from deletion or overwrite; it does not
serialize Terraform operations or indicate that one Terraform process owns the
state. It is therefore not a substitute for Terraform state locking.

Do not configure default Object Lock retention as the baseline for a Terraform
state bucket containing `.tflock` objects. AWS applies bucket default retention
to every new object version placed in the bucket. That includes lock-file
versions. In a versioned bucket, a normal `DeleteObject` request can create a
delete marker without permanently deleting protected lock-file versions, so
default retention does not always prevent a normal Terraform unlock. The
stronger operational risk is the accumulation of protected `.tflock` versions,
permanent cleanup complexity, recovery complexity, and the governance or
compliance overhead required to manage them. Terraform requires
`s3:DeleteObject` on the `.tflock` object for normal lock cleanup.

Do not use blanket Object Lock default retention for a bucket containing
`.tflock` files unless a separate reviewed design explicitly handles lock-file
cleanup and operational recovery.

Versioning plus restrictive IAM delete permissions is the safer baseline for
this project. Object-level retention for selected, verified state versions may
be considered only as an advanced manual recovery or audit control with a
separately reviewed procedure. It must not become the default operating model.

## Least-privilege access

Use separate normal-deployer and break-glass roles. Scope resource ARNs and
`s3:prefix` conditions to the exact reviewed bucket and state prefix.

### Normal deployer role

Grant only the backend permissions required for normal operation:

| Resource | Required permissions |
| --- | --- |
| State bucket and exact state prefix | Narrowly scoped `s3:ListBucket` |
| Real `terraform.tfstate` object | `s3:GetObject`, `s3:PutObject` |
| Matching `.tflock` object | `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` |

Do not grant the normal deployer role `s3:DeleteObject` or
`s3:DeleteObjectVersion` for the real state object. Terraform's S3 backend does
not require `s3:DeleteObject` on the state object for normal operation.

The bucket policy should also deny non-TLS requests and prevent access outside
the reviewed identities and administrative recovery path. Avoid broad wildcard
resources and actions.

### Break-glass or administrative role

Keep the recovery role restricted, audited, and unavailable to normal Terraform
runs. It may have narrowly scoped recovery permissions such as
`s3:DeleteObject` or `s3:DeleteObjectVersion` for state versions only when a
documented incident procedure requires them. Require explicit approval,
short-lived credentials, and audit notes for every use.

### KMS permissions

For SSE-KMS, grant the backend identity only these required cryptographic
permissions, narrowly scoped to the exact customer-managed KMS key:

- `kms:Encrypt`
- `kms:Decrypt`
- `kms:GenerateDataKey`

Grant `kms:DescribeKey` separately only when operational verification requires
it. Review both IAM policy and KMS key policy, and validate the effective
minimum from audited backend activity before removing permissions.

### Control-plane protection

The normal Terraform deployment identity must not be able to delete the state
bucket, alter its bucket policy, suspend versioning, change encryption
settings, delete current or noncurrent state object versions, disable the KMS
key, schedule KMS key deletion, or bypass audit controls.

Keep administrative recovery or break-glass access separate from normal
Terraform operations. Protect and audit that access, require explicit approval
and short-lived credentials, and record every use without exposing state
contents.

## Safe migration checklist

The following steps describe a future, separately approved manual operations
process. They are not commands to run during documentation or readiness work.

1. Pause all Terraform activity before backup or migration. This gate includes
   local operators, CI jobs, scheduled drift checks, and every other automation
   that can read or modify the same infrastructure or state.
2. **Future manual operator check:** run `terraform version` and confirm that
   every operator and automation environment uses Terraform `>= 1.10.0`.
3. Verify that the reviewed branch is active and that the working tree is
   clean.
4. Identify and verify the current authoritative state source without printing
   or parsing state contents. The mere presence of a local `terraform.tfstate`
   file is not proof that it is complete, current, or authoritative. Complete
   this step before copying any local state.
5. Create a sensitive, external backup of the authoritative state without
   committing it. Future backup commands must first set restrictive permissions
   such as `umask 077`, and the backup must be stored outside the repository in
   an access-controlled location. Record a checksum without exposing state
   contents, and document the backup owner and recovery procedure.
6. Bootstrap the dedicated backend bucket, KMS key, policies, roles,
   versioning, encryption, and auditing separately from the main Terraform
   stack.
7. Verify backend controls and wait for newly enabled S3 Versioning to propagate
   before any state write. AWS recommends waiting 15 minutes after first
   enabling versioning before issuing object writes.
8. Review and add the backend block only after all preceding controls and
   placeholders have approved values.
9. **Future manual operator step:** run `terraform init -migrate-state` only
   with explicit approval and exclusive Terraform access.
10. **Future manual operator step:** verify the expected resource addresses with
    `terraform state list` without exposing state contents.
11. **Future manual operator step:** run `terraform plan -refresh-only` as a
    conservative verification step. It accesses the backend and may read live
    AWS resources.
12. **Future manual operator step:** after successful refresh-only review, run
    `terraform plan` and investigate every unexpected change.
13. Complete the post-migration verification checklist below.
14. Do not run `terraform apply` until state integrity, locking, versioning,
    permissions, auditability, and recoverability are independently verified.
15. Do not delete the external backup until remote-state integrity, version
    retention, locking behavior, and recovery are independently verified and an
    authorized operator explicitly approves removal.

Record approvals, timestamps, operator identities, source and destination
locations, verification outcomes, and any unexpected behavior without
recording state contents or secrets.

## Future post-migration verification checklist

This checklist is documentation for a future approved migration. Do not execute
these checks as part of documentation or readiness work.

- Confirm that the remote state object exists and uses SSE-KMS with the approved
  customer-managed KMS key.
- Confirm that state object versioning is active and that at least one state
  object version exists after the approved migration.
- During a future approved locked operation, confirm that the matching
  `.tflock` object is created and removed.
- Confirm that concurrent Terraform runs against the same state are blocked.
- Confirm that the normal Terraform role cannot delete the real state object or
  any current or noncurrent state object version.
- Confirm that the external state backup still exists and that its checksum
  matches the recorded pre-migration checksum.
- Confirm CloudTrail or equivalent audit visibility for state access.
- Confirm that recovery from a known-good state version is documented and
  tested without exposing state contents.

## Rollback and recovery principles

Recovery must begin from either an independently verified external state backup
or a known-good S3 object version. Stop concurrent Terraform activity before
diagnosis or recovery. Preserve the current remote version and all available
evidence before attempting replacement.

Do not use `terraform state push`, `terraform state rm`, `terraform apply`, or
`terraform destroy` as casual recovery tools. Any state replacement or mutation
requires explicit operator approval, a fresh backup, a reviewed recovery plan,
and audit notes. Validate the restored state's resource addresses and a
refresh-only plan before considering normal operations.

## Workspace design note

This project must use only the Terraform default workspace unless a separate
workspace design is reviewed and approved before use. For the default
workspace, grant `s3:DeleteObject` only on the matching `.tflock` object and do
not grant it on the real state object.

If non-default workspaces are ever introduced, redesign and review the S3 path
layout and IAM permissions before use. Design `key` and `workspace_key_prefix`
deliberately, and keep environment state in unambiguous, separately authorized
prefixes. HashiCorp documents that the default workspace uses the configured
`key`, while non-default workspaces add a workspace prefix; an accidental
prefix design can therefore mix environment state or permissions.

## Official references

- HashiCorp Terraform:
  [S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3),
  [Terraform 1.10 S3 backend](https://developer.hashicorp.com/terraform/language/v1.10.x/backend/s3),
  and [state locking](https://developer.hashicorp.com/terraform/language/state/locking)
- AWS:
  [Amazon S3 data consistency model](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html#ConsistencyModel),
  [S3 Versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html),
  and [default bucket encryption](https://docs.aws.amazon.com/AmazonS3/latest/userguide/default-bucket-encryption.html)
- AWS:
  [S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html),
  [S3 security best practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html),
  and [S3 CloudTrail events](https://docs.aws.amazon.com/AmazonS3/latest/userguide/cloudtrail-logging-s3-info.html)
- AWS:
  [S3 Bucket Keys](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-key.html)
  and [AWS KMS key rotation](https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html)
