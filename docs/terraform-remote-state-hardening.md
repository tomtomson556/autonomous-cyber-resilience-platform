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

Do not print, parse, commit, or expose Terraform state while following this
runbook. State can contain sensitive values even when the corresponding
Terraform outputs are marked sensitive.

## Current project observations

- The main Terraform root module manages the S3 lab/application bucket. The
  remote-state bucket must be a different bucket with an independent lifecycle.
- The checked-in Terraform configuration contains no backend block.
- No checked-in Terraform workspace configuration or documented workspace
  operating model was found. This does not prove that workspaces have never
  been used locally.
- The Terraform configuration currently allows Terraform `>= 1.5.0`. Native S3
  lockfile locking with `use_lockfile` was introduced as experimental in
  Terraform `1.10`; all operators and automation must therefore use Terraform
  `>= 1.10` before this design is adopted. Changing the project's
  `required_version` is outside this documentation-only change.
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
- Enable server-side encryption. SSE-S3 is the lowest-cost baseline. SSE-KMS
  with a customer-managed KMS key and key rotation is an optional stronger
  control when its additional key-policy, availability, and cost requirements
  are understood.
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

For an approved SSE-KMS design, the reviewed configuration may additionally
refer to a placeholder KMS key ARN:

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
versions. A simple delete can still create a delete marker, but permanently
deleting a retained lock-file version can fail or require governance-bypass
permissions. Default retention therefore complicates stale-lock cleanup and
recovery without replacing Terraform's locking protocol. Terraform requires
`s3:DeleteObject` on the `.tflock` object for normal lock cleanup.

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

If SSE-KMS is selected, grant only the KMS permissions the reviewed backend
operation requires, normally:

- `kms:Encrypt`
- `kms:Decrypt`
- `kms:GenerateDataKey`
- `kms:DescribeKey`

Scope access to the exact customer-managed KMS key and review both IAM policy
and key policy. Validate the effective minimum from audited backend activity
before removing permissions.

## Safe migration checklist

The following steps are a controlled migration plan, not commands to run during
documentation work.

1. Pause all Terraform activity, including local operators and automation.
2. Verify the current Git branch and require a clean working tree.
3. Identify and verify the current authoritative state source without printing
   or parsing state contents. Do not assume that a local state file is complete
   or current.
4. Create an external, access-controlled backup of the recovered or local state
   file without committing it. Independently verify the backup and recovery
   ownership.
5. Bootstrap the dedicated backend bucket, optional KMS key, policies, roles,
   versioning, encryption, and auditing separately from the main Terraform
   stack.
6. Verify backend controls and wait for newly enabled S3 Versioning to propagate
   before any state write. AWS recommends waiting 15 minutes after first
   enabling versioning before issuing object writes.
7. Review and add the backend block only after all preceding controls and
   placeholders have approved values.
8. **Manual operator step:** run `terraform init -migrate-state` only with
   explicit approval and exclusive Terraform access.
9. **Manual operator step:** verify the expected resource addresses with
   `terraform state list` without exposing state contents.
10. **Manual operator step:** run `terraform plan -refresh-only` as a
    conservative verification step. It accesses the backend and may read live
    AWS resources.
11. **Manual operator step:** after successful refresh-only review, run
    `terraform plan` and investigate every unexpected change.
12. Verify native lockfile behavior, state version creation, encryption,
    least-privilege permissions, audit events, and recovery from a known-good
    noncurrent version.
13. Do not run `terraform apply` until state integrity, locking, versioning,
    permissions, auditability, and recoverability are independently verified.
14. Do not remove local state copies until remote-state integrity,
    recoverability, required retention, and external backups are independently
    verified and an authorized operator explicitly approves removal.

Record approvals, timestamps, operator identities, source and destination
locations, verification outcomes, and any unexpected behavior without
recording state contents or secrets.

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

This repository does not currently appear to define or document Terraform
workspaces. This conclusion is based only on checked-in configuration and
documentation and does not establish the state of any operator's local
Terraform metadata.

If workspaces are introduced, design `key` and `workspace_key_prefix`
deliberately before use. Keep lab, production, and default-workspace state in
unambiguous, separately authorized prefixes. HashiCorp documents that the
default workspace uses the configured `key`, while non-default workspaces add a
workspace prefix; an accidental prefix design can therefore mix environment
state or permissions.

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
