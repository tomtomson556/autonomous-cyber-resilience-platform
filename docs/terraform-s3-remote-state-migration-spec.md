# Terraform S3 Remote State Migration Specification

## Purpose and status

This document is a decision-ready specification template for a future,
controlled introduction of Amazon S3 remote state. It is not an execution
runbook. No migration approval, implementation, or verification has occurred.
All environment-specific values and approvals remain unresolved.

| Field | Value |
| --- | --- |
| Decision status | `TBD` |
| Approval status | `TBD` |
| Responsible operator | `TBD` |
| Reviewer | `TBD` |
| Approval date | `TBD` |
| Planned maintenance window | `TBD` |

The future migration must follow the
[Terraform remote state hardening runbook](terraform-remote-state-hardening.md)
and a separately approved manual operations process.

## Scope and non-goals

### Scope

- Define decisions, controls, approvals, gates, and responsibilities for a
  future controlled introduction of S3 remote state.
- Define the target S3, KMS, IAM, locking, auditing, backup, and recovery
  requirements.
- Define future Go/No-Go, abort, retry, communication, and verification
  requirements.

### Non-goals

- No current backend migration or backend configuration activation.
- No current infrastructure creation or modification.
- No Terraform or AWS execution.
- No real state-file access or discovery of environment-specific values.
- No deletion of old local state copies.
- No DynamoDB locking design.

## Preconditions and dependencies

The future migration cannot begin until all of the following are satisfied:

- PR #56 remote-state readiness changes are present.
- Every operator and automation environment is verified to use Terraform
  `>= 1.10.0`.
- Only the default Terraform workspace is in scope. Any non-default workspace
  requires a separate reviewed and approved design.
- All local Terraform activity, CI jobs, scheduled drift checks, and other
  Terraform automation are paused.
- The authoritative current state source is identified and approved before any
  backup or migration.
- A secure recovery backup is completed and independently verified.
- Required operators, reviewers, backup owners, audit owners, and escalation
  contacts are assigned.
- The maintenance window, communication channel, rollback path, and
  post-migration verification checklist are approved.

## Decision fields

Every field must be resolved, reviewed, and approved before the future
migration begins.

| Decision | Unresolved value | Owner | Approval |
| --- | --- | --- | --- |
| AWS account ID | `TBD_ACCOUNT_ID` | `TBD` | `TBD` |
| AWS region | `TBD_REGION` | `TBD` | `TBD` |
| S3 state bucket name | `TBD_STATE_BUCKET_NAME` | `TBD` | `TBD` |
| Backend key path | `TBD_BACKEND_KEY` | `TBD` | `TBD` |
| KMS key model | `TBD_KMS_KEY_MODEL` | `TBD` | `TBD` |
| Full KMS key ARN | `TBD_KMS_KEY_ARN` | `TBD` | `TBD` |
| Normal deployer role ARN | `TBD_DEPLOYER_ROLE_ARN` | `TBD` | `TBD` |
| Break-glass role ARN | `TBD_BREAK_GLASS_ROLE_ARN` | `TBD` | `TBD` |
| Backup storage location | `TBD_BACKUP_LOCATION` | `TBD` | `TBD` |
| Backup owner | `TBD_BACKUP_OWNER` | `TBD` | `TBD` |
| Backup checksum | `TBD_BACKUP_CHECKSUM` | `TBD` | `TBD` |
| Audit and logging owner | `TBD_AUDIT_OWNER` | `TBD` | `TBD` |
| Communication channel | `TBD_COMMUNICATION_CHANNEL` | `TBD` | `TBD` |
| Escalation contact | `TBD_ESCALATION_CONTACT` | `TBD` | `TBD` |

## Target control-plane requirements

The approved target design must:

- Use a dedicated S3 bucket with an independent lifecycle from the main
  Terraform-managed infrastructure.
- Enable S3 Versioning before the first state write.
- Enable SSE-KMS with a customer-managed KMS key and approved key rotation.
- Enable all four S3 Block Public Access settings.
- Set S3 Object Ownership to `BucketOwnerEnforced` so ACLs are disabled.
- Enforce TLS-only access through bucket policy.
- Implement least-privilege IAM with separate normal deployer and break-glass
  roles.
- Protect the S3 and KMS control plane from the normal deployer role. The role
  must not be able to delete the bucket, alter bucket policy, suspend
  versioning, change encryption, disable the KMS key, schedule KMS key deletion,
  or bypass audit controls.
- Deny the normal deployer role `s3:DeleteObject` and
  `s3:DeleteObjectVersion` on the real state object and its versions.
- Grant `s3:DeleteObject` only on the matching `.tflock` object where required
  for lockfile cleanup.
- Grant only narrowly scoped S3 and KMS data-plane permissions required for
  normal backend operation.
- Record S3 object-level state access through CloudTrail S3 data events or an
  explicitly approved equivalent audit solution.

Administrative or break-glass access must be separately protected, explicitly
approved, short-lived, and auditable.

### Normal deployer role

The normal deployer role must be restricted to the approved bucket, backend
key, KMS key, and matching lockfile. Its reviewed data-plane permissions must
be limited to:

- Narrowly scoped `s3:ListBucket` for the approved state prefix.
- `s3:GetObject` and `s3:PutObject` for the real state object.
- `s3:GetObject`, `s3:PutObject`, and `s3:DeleteObject` for the matching
  `.tflock` object.
- `kms:Encrypt`, `kms:Decrypt`, and `kms:GenerateDataKey` for the exact approved
  customer-managed KMS key.
- `kms:DescribeKey` only if the approved operational verification requires it.

The final IAM and KMS key policies must be independently reviewed before use.

### Break-glass role

The break-glass role must not be used for normal Terraform operations. Its
approved permissions, activation method, approvers, credential lifetime, audit
requirements, and deactivation process must be documented before migration.
Every activation must require explicit approval and produce an auditable
record. Recovery permissions must be narrowly scoped to the approved recovery
procedure.

## Locking model

- Native S3 lockfiles with Terraform `use_lockfile = true` are required.
- No new DynamoDB locking table is planned.
- Introducing DynamoDB locking requires a separate reviewed and approved design
  decision.
- Future verification must confirm lock acquisition, lock cleanup, and
  prevention of concurrent Terraform operations against the same state.

## Backup and recovery requirements

- Complete a secure backup of the approved authoritative state before the
  future migration.
- Store the backup outside the project and any project ZIP in an
  access-controlled location.
- Assign and document the backup owner.
- Record and independently verify a checksum during the future operations
  process without exposing state contents.
- Document and review the recovery procedure before migration.
- Define backup retention and access-audit requirements before migration.
- Do not delete old local state copies until remote-state integrity, independent
  verification, backup retention, rollback criteria, and recovery capability
  are approved.

## Go / No-Go gates

Every gate requires a recorded pass before the future migration begins.

| Gate | Status | Approver | Evidence reference |
| --- | --- | --- | --- |
| Reviewed branch active and worktree clean | `TBD` | `TBD` | `TBD` |
| Maintenance window approved | `TBD` | `TBD` | `TBD` |
| Terraform automation paused | `TBD` | `TBD` | `TBD` |
| Authoritative state source confirmed | `TBD` | `TBD` | `TBD` |
| Secure backup completed | `TBD` | `TBD` | `TBD` |
| Backup checksum recorded and verified | `TBD` | `TBD` | `TBD` |
| Target bucket, KMS key, and IAM reviewed | `TBD` | `TBD` | `TBD` |
| Normal and break-glass access model reviewed | `TBD` | `TBD` | `TBD` |
| Rollback and recovery path reviewed | `TBD` | `TBD` | `TBD` |
| Communication channel active | `TBD` | `TBD` | `TBD` |
| Post-migration verification checklist ready | `TBD` | `TBD` | `TBD` |

Any unresolved or failed gate results in No-Go.

## Abort criteria

Abort the future migration without proceeding to further state-changing
operations if any of the following occurs:

- The authoritative state source is ambiguous or cannot be confirmed.
- Backup creation or verification fails.
- The recorded backup checksum does not match.
- Terraform reports unexpected drift or changes that are not understood.
- Lock acquisition or cleanup fails.
- Required IAM or KMS permission is missing or broader than approved.
- An unexpected Terraform workspace is active or discovered.
- Account, region, bucket, backend key, KMS key, or role values are unapproved
  or differ from the decision record.
- The rollback or recovery path is unclear or cannot be executed safely.
- Terraform automation cannot be confirmed as paused.
- Audit visibility or required communication is unavailable.

## Retry criteria after abort

An aborted migration may be attempted again only when:

- The root cause is documented and resolved.
- The authoritative state source is reconfirmed.
- The secure backup and checksum are reconfirmed.
- No competing Terraform run occurred after the abort.
- Operator and reviewer approvals are renewed.
- All updated Go/No-Go gates pass.
- The maintenance window, communication channel, rollback path, and audit
  visibility are reconfirmed.

## Future manual operation outline

The following is a high-level outline for a future, separately approved manual
operations process. It contains no executable commands and was not executed as
part of this documentation change.

1. Open the approved maintenance window and activate the communication channel.
2. Pause and independently confirm the pause of all Terraform automation.
3. Reconfirm the approved decisions, default workspace, authoritative state
   source, backup, checksum, and Go/No-Go gates.
4. Verify the separately bootstrapped S3, KMS, IAM, locking, and audit controls.
5. Review the final backend configuration against approved decision fields.
6. Perform the approved backend migration under exclusive operator control.
7. Stop and follow the approved abort and rollback process on any unexpected
   result.
8. Complete and record every post-migration verification check.
9. Obtain explicit approval before resuming Terraform automation.
10. Retain old local state copies until retention and recovery approval is
    recorded.

## Post-migration verification checklist

These are future checks for a separately approved operations process. They were
not executed or validated as part of this documentation change.

- [ ] Backend initialization targets the approved bucket and backend key.
- [ ] Native S3 lockfile creation, contention handling, and cleanup are
      confirmed.
- [ ] Expected state resource addresses are reviewed without exposing state
      contents.
- [ ] A refresh-only plan is reviewed and all results are understood.
- [ ] A normal plan is reviewed and all results are understood.
- [ ] S3 state object versioning is observed.
- [ ] SSE-KMS with the approved customer-managed KMS key is confirmed.
- [ ] CloudTrail S3 data events or the approved equivalent audit solution are
      confirmed.
- [ ] The normal deployer role cannot delete the real state object or its
      versions.
- [ ] The external backup and its checksum remain independently verifiable.
- [ ] Old local state copies remain retained pending retention and recovery
      approval.
- [ ] Recovery from a known-good version is documented and tested without
      exposing state contents.
- [ ] The migration decision record is updated with results, approvals, and
      evidence references.

## Communication and escalation

| Responsibility | Assigned value |
| --- | --- |
| Pause Terraform automation | `TBD` |
| Independently confirm automation pause | `TBD` |
| Approve resume of Terraform automation | `TBD` |
| Communication channel | `TBD_COMMUNICATION_CHANNEL` |
| Escalation contact | `TBD_ESCALATION_CONTACT` |
| Record final migration result | `TBD` |

The future migration result must be recorded in the approved decision record
with timestamps, operator and reviewer identities, gate outcomes, verification
results, evidence references, aborts, retries, and final approval. The record
must not contain state contents, credentials, secrets, or sensitive backend
configuration.
