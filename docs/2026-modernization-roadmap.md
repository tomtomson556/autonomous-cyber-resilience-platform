# 2026 Modernization Roadmap

## Strategic direction

This repository is evolving from an AWS S3 security validator into an
AI-assisted Cyber-Resilience SOAR platform for backup and recovery security.
The current read-only S3 security evidence collector and rule-based validator
are the first implemented evidence source.

In this project, SOAR means controlled Security Orchestration, Automation and
Response for Backup Resilience. It does not mean fully autonomous production
automation. AI provides advisory analysis, prioritization, summaries, reports,
and proposals. Deterministic policy checks and human approvals remain the final
authorization authority for critical actions.

The repository remains a lab, portfolio, and prototype project. The roadmap
prioritizes reliable evidence and deterministic evaluation before AI assistance
and controlled orchestration.

## Implemented baseline

- Read-only validation of S3 versioning, approved server-side encryption,
  Object Lock capability, full Block Public Access, non-public bucket policy
  status, TLS-only access, and `BucketOwnerEnforced` object ownership.
- Terraform-managed S3 lab bucket with Object Lock enabled at creation,
  Governance mode, and a 1-day default retention period.
- GitHub Actions OIDC validation through a dedicated read-only AWS role.
- Structured check results with `status`, `reason`, and `message`.
- Check-level `PASS`, `FAIL`, and `UNKNOWN` statuses and overall `SECURE`,
  `INSECURE`, and `INCOMPLETE` statuses.
- Versioned `s3-security-report/v1` evidence contract with consistent
  `UNKNOWN` semantics for inaccessible, incomplete, or malformed evidence.

## Foundation Gate: Evidence contract and S3 source stability

Foundation Gate status: initial S3 evidence contract v1 stabilized with
regression coverage.

- Stabilize the S3 evidence source and its regression coverage.
- Apply the documented `UNKNOWN` semantics consistently across all independently
  evaluable checks.
- Define and version the structured Security Report Contract.
- Preserve rule-based validators as the authoritative source for `PASS`, `FAIL`,
  and `UNKNOWN`.

The S3 evidence source implements the status model across every validator check
and individual `AccessDenied` path. Missing, inaccessible, incomplete, or
malformed evidence is not presented as a confirmed security failure.

## Milestone 1: Unified resilience evidence and Veeam visibility

- Define a versioned Unified Resilience Report Schema.
- Map the versioned S3 Security Report v1 into the unified schema with a
  deterministic local adapter.
- Implement a Veeam API read-only collector.
- Produce example reports for backup jobs, repositories, restore points, and
  storage targets.
- Map source evidence, collection timestamps, and confidence or completeness
  information into the unified schema.

## Milestone 2: Deterministic resilience evaluation

- Implement deterministic RPO and RTO evaluation rules.
- Add restore-test evidence.
- Add cross-source risk scoring based on explicit, reviewable rules.
- Keep scores as prioritization aids rather than final authorization decisions.

## Milestone 3: Workload context and historical evidence

- Add Microsoft 365 and hybrid workload metadata.
- Compare historical resilience reports.
- Detect configuration and evidence drift.
- Preserve source timestamps and provenance for every comparison.

## Milestone 4: AI-assisted prioritization and reporting

- Add AI-assisted prioritization, explanation, and report drafting.
- Introduce an enterprise-controlled AI advisory and prioritization layer.
- Keep AI outputs advisory, not authoritative.
- Restrict external AI services to non-critical support tasks such as
  summarization, wording, documentation, and drafting.

The enterprise-controlled AI advisory and prioritization layer that influences
operational prioritization or action
proposals must run locally or in an environment technically, organizationally,
and contractually controlled by the enterprise.

## Milestone 5: Controlled orchestration

- Define versioned runbook metadata.
- Add deterministic policy gates.
- Add an explicit human approval workflow.
- Add controlled orchestration through least-privilege execution identities.
- Audit analyses, proposals, policy decisions, approvals, and resulting actions.

AI may propose candidate runbooks and prepare reviewable parameters. It must not
select, authorize, or execute critical runbooks independently.

## Parallel backlog

- Add SSE-KMS with customer-managed keys and key rotation.
- Add AWS-native detection evidence.
- Add IAM Access Analyzer evidence.
- Add SBOM and supply-chain evidence.
- Continue S3 evidence source hardening.
- Evaluate temporary credentials and separately approved deployment workflows.

## Apply notes

Object Lock is intentionally strong. Once enabled on a bucket, it cannot be
disabled, and versioning cannot be suspended. The Terraform-managed lab bucket
provisions Object Lock at bucket creation time and applies a 1-day default
retention period in Governance mode. Existing buckets without Object Lock
should be treated carefully because enabling Object Lock later can require
replacement or an explicitly reviewed migration path.
