# Terraform State Bootstrap Architecture Decision

## Status

**Proposed / pending approval.** The recommendation in this document is not
operatively approved or implemented.

## Context

The project has not migrated its local Terraform state to a production remote
backend. The
[remote state hardening runbook](terraform-remote-state-hardening.md) defines
the target security controls, and the
[S3 remote state migration specification](terraform-s3-remote-state-migration-spec.md)
defines future migration decisions and gates.

This document adds only the remaining bootstrap architecture decision. It does
not duplicate those existing documents.

## Decision scope

This decision covers only how the future remote-state control plane is
bootstrapped and independently managed. It adds no Terraform or CloudFormation
code, performs no AWS or Terraform execution, migrates no state, and does not
change the existing Terraform root.

## Problem statement

The remote-state control plane must exist before the existing Terraform root
can use it. That control plane must not depend on the backend it is creating.
Its bootstrap state, when applicable, or its authoritative configuration must
also be protected, recoverable, reviewable, and auditable.

## Options considered

All options require a lifecycle and permission boundary separate from the
existing Terraform root.

| Criterion | Separate Terraform bootstrap root without remote backend initially | CloudFormation-based bootstrap | Controlled manual bootstrap |
| --- | --- | --- | --- |
| Circular dependency risk | Low when its initial state is independently protected | Low; no Terraform backend dependency | Low; no Terraform backend dependency |
| Authoritative configuration | Reviewed Terraform configuration in a dedicated root | Reviewed CloudFormation template | Approved procedure and decision record |
| Bootstrap state | Initially local and separately protected; later disposition requires approval | CloudFormation stack state managed by AWS | No tool state; evidence and approved configuration record are authoritative |
| State/configuration protection | Restricted external storage, ownership, retention, and audit controls | Template protection plus restricted stack and account permissions | Restricted procedure, evidence, and access-controlled records |
| Reproducibility | High | High | Lower and operator-dependent |
| Reviewability | High and aligned with existing Terraform skills | High, but introduces another infrastructure language | Moderate; depends on procedure and evidence quality |
| Drift detection | Requires an approved bootstrap-root drift process | CloudFormation drift detection plus approved review process | Requires separate detective controls and reconciliation |
| Recovery complexity | Moderate; recover bootstrap state or reconstruct under approval | Moderate; recover or reconcile stack and template | Higher; reconstruct from approved records and evidence |
| Permission isolation | Strong when separate identities and lifecycle controls are enforced | Strong when stack administration is isolated | Strong only with tightly controlled operator access |
| Operational effort | Moderate | Moderate | Low initially, higher for repeatability and recovery |
| Dependencies and failure risks | Terraform tooling and protected bootstrap-state custody | CloudFormation expertise and stack availability | Human error, incomplete evidence, and procedural drift |
| Audit approach | Version control plus bootstrap-state and API activity audit | Version control plus stack and API activity audit | Approval records, API activity audit, and retained evidence |
| Residual risks | Protected local bootstrap state remains a sensitive dependency | Split toolchain and stack-level administrative risk | Weakest reproducibility and highest operator dependence |

## Recommended option

Adopt a **separate bootstrap lifecycle**, preferably a dedicated Terraform
bootstrap root or an approved equivalent method. The final method remains
pending approval.

The approved design must:

- Avoid a backend or state circular dependency.
- Keep ownership, permissions, change control, audit, drift detection, and
  recovery separate from the existing Terraform root.
- Protect the bootstrap state or authoritative configuration independently.
- Require separate approval before any operational bootstrap or migration.
- Preserve native S3 lockfile locking with `use_lockfile = true` for the future
  application backend and introduce no new DynamoDB locking design.

This recommendation does not authorize implementation. This PR performs no
`terraform apply` and adds no backend block to the existing root module.

## Alternatives and tradeoffs

CloudFormation remains a viable equivalent when the organization accepts a
second infrastructure language and assigns stack ownership, drift detection,
and recovery responsibilities. A controlled manual procedure remains possible
for a narrowly scoped one-time bootstrap, but it has weaker reproducibility and
greater dependence on operator evidence and discipline.

No option is considered implemented until its ownership, protection, recovery,
audit, and approval model is resolved.

## Approval and unresolved decisions

| Decision | Recommended direction | Status | Owner | Approval |
| --- | --- | --- | --- | --- |
| Existing AWS account or separate control-plane account | Prefer stronger lifecycle and permission isolation | `TBD` | `TBD` | `TBD` |
| Ownership and responsibility | Assign a dedicated control-plane owner | `TBD` | `TBD` | `TBD` |
| Final bootstrap method | Separate Terraform bootstrap root or approved equivalent | `TBD` | `TBD` | `TBD` |
| Bootstrap state or authoritative configuration custody | External, access-controlled, recoverable, and audited | `TBD` | `TBD` | `TBD` |
| Normal deployment role | Separate least-privilege identity | `TBD` | `TBD` | `TBD` |
| Break-glass role | Separate, protected, short-lived, and audited | `TBD` | `TBD` | `TBD` |
| Audit solution | CloudTrail S3 data events or approved equivalent | `TBD` | `TBD` | `TBD` |
| Drift detection | Method-specific reviewed process | `TBD` | `TBD` | `TBD` |
| Bucket, KMS, and critical configuration deletion protection | Protect outside normal deployment permissions | `TBD` | `TBD` | `TBD` |

## Non-goals

- No AWS or Terraform execution.
- No state migration or state-file access.
- No backend block in the existing Terraform root.
- No productive resource changes.
- No real AWS values, credentials, or secrets.
- No bootstrap implementation or approval.

## Follow-up PRs

1. Add bootstrap code or an approved bootstrap template only after this
   decision is approved.
2. Specify KMS and IAM least-privilege details based on the final bootstrap
   decision.
3. Perform the operational migration only through a separate, manually approved
   process.
