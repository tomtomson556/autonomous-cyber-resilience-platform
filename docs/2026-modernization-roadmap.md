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
- Deterministic local S3-to-unified adapter.
- `veeam-evidence-report/v1` contract with a shipped `mock_only` example and a
  reserved, non-networking `api_read_only` collector profile.
- Deterministic local Veeam-to-unified adapter with no Veeam API or network
  access.
- Deterministic local `rpo-rto-policy/v1` evaluation producing separate
  `resilience-evaluation-report/v1` output without modifying Unified evidence.
- Local versioned `restore-test-evidence/v1` contract and deterministic
  validator with structured restore-validation attestations and no restore
  execution or network access.
- Optional deterministic RTO evaluation from exactly matched, validated
  `restore-test-evidence/v1`, without modifying Unified evidence.

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
- Stabilize the mock-based Veeam Evidence Report v1 contract and deterministic
  unified adapter.
- Add a deterministic local Unified Resilience Report composer that preserves
  source evidence and provenance while rejecting duplicate identifiers and
  incompatible classifications.
- Define the `api_read_only` collector profile and safety boundary in
  `veeam-evidence-report/v1`.
- Implement network-free Veeam Enterprise Manager collector groundwork with
  fake-response tests and an enforced method and endpoint allowlist.
- Add a pre-transport API-contract fixture and conservative mapping step using
  sanitized Veeam Enterprise Manager resource patterns.
- Add deterministic `api_read_only` completeness findings for observed
  resources that cannot be mapped because required relationships or values are
  missing, unlinked, contradictory, or ambiguous.
- Preserve `UNKNOWN` semantics and omit affected resources from normal mapped
  collections instead of inventing relationships or identifiers.
- Keep current sanitized fixtures single-page only; pagination remains future
  work.
- Later add a separately reviewed productive read-only transport without
  weakening the reviewed safety boundary. Real authentication, logon,
  session-manager, TLS, certificate handling, secret acquisition, and
  pagination remain future work.
- Later decide an explicit Unified Resilience Report adapter policy for
  `api_read_only` evidence.
- Preserve the no-write, no-restore, and no-direct-API-to-unified-report
  boundary throughout these steps.
- Map source evidence, collection timestamps, and confidence or completeness
  information into the unified schema.

The current branch still implements no productive HTTP client, authentication,
TLS or certificate handling, secret acquisition, write, restore, mutation, or
job-control operation. The Unified Resilience Report adapter continues to reject
`api_read_only`. The local composer only combines existing Unified Resilience
Reports and introduces no external API access.

## Milestone 2: Deterministic resilience evaluation

- Implement deterministic RPO evaluation rules and a compatible RTO `UNKNOWN`
  fallback when restore-test evidence is not supplied.
- Integrate validated `restore-test-evidence/v1` into a separately reviewed
  deterministic RTO evaluation pipeline.
- Add cross-source risk scoring based on explicit, reviewable rules.
- Keep scores as prioritization aids rather than final authorization decisions.

The evaluator now optionally accepts one validated local restore-test evidence
report. It calculates RTO only from one exact, unambiguous asset match and
preserves `UNKNOWN` for missing, ambiguous, inconclusive, or future-dated
evidence. Risk scoring remains a later, separate step.

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
- Move local Terraform state toward a dedicated, separately bootstrapped S3
  backend with versioning, least-privilege access, and native S3 lockfile
  locking. Follow the documentation-only
  [Terraform remote state hardening runbook](terraform-remote-state-hardening.md);
  productive migration remains a separately approved operations-hardening step.

## Apply notes

Object Lock is intentionally strong. Once enabled on a bucket, it cannot be
disabled, and versioning cannot be suspended. The Terraform-managed lab bucket
provisions Object Lock at bucket creation time and applies a 1-day default
retention period in Governance mode. Existing buckets without Object Lock
should be treated carefully because enabling Object Lock later can require
replacement or an explicitly reviewed migration path.
