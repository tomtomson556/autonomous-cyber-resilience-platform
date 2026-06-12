# Unified Resilience Report Schema

## Purpose

The Unified Resilience Report Schema defines a versioned, source-neutral
contract for backup and recovery resilience evidence. It provides a common
structure for deterministic evaluation, reporting, historical comparison, and
future controlled SOAR workflows.

This document is a Foundation Gate for future Veeam, Microsoft cloud and hybrid,
AWS, and controlled SOAR evidence correlation. It defines the planned contract;
it does not imply that those collectors or orchestration capabilities are
already implemented.

This is a prototype contract for the lab and portfolio project. It is not a
production-ready integration specification.

The initial contract version is `1.0.0`. Producers should include
`schema_version` in every report so that consumers can validate compatibility
before processing evidence.

## Relationship to Current S3 Security Reports

The AWS S3 security validator produces source-specific reports with structured
check results containing `status`, `reason`, and `message`. The local
`s3_unified_report_adapter` maps versioned `s3-security-report/v1` reports into
the unified report without changing the S3 validator's authority over its
rule-based results.

The unified report does not replace source reports. It references and correlates
their evidence so that backup assets can be evaluated across storage,
protection, recovery, and workload context.

The adapter deterministically maps S3 `SECURE`, `INSECURE`, and `INCOMPLETE`
overall statuses to unified `HEALTHY`, `AT_RISK`, and `INCOMPLETE` statuses. It
also preserves the original S3 overall status and every check-level `PASS`,
`FAIL`, and `UNKNOWN` result. It does not calculate risk scores or recommend
actions; those asset fields remain `null` and `recommended_actions` remains
empty.

## Composing Existing Unified Reports

The local `unified_report_composer` combines two or more existing Unified
Resilience Reports without collecting new evidence. It validates the input
contract, rejects duplicate source, asset, finding, and action identifiers, and
sorts merged collections deterministically.

The composer preserves input assets, evidence sources, findings, actions, and
`UNKNOWN` semantics without reinterpretation. Its overall status is calculated
conservatively from input overall statuses and findings. `CRITICAL` has
precedence over `AT_RISK`, followed by `INCOMPLETE` and `HEALTHY`.

All inputs must use the same `data_classification`; the project defines no
implicit classification downgrade or escalation rule. Composer provenance
records stable input identifiers, timestamps, schema versions, report types,
evidence-source identifiers, and input overall statuses.

The CLI accepts existing local JSON reports:

```bash
python -m src.tools.unified_report_composer INPUT... --output OUTPUT
```

It does not overwrite inputs or an existing output file. The composer performs
no network requests and introduces no Veeam transport, authentication, TLS,
secret handling, restore, mutation, or job-control behavior.

## Evidence Sources

`evidence_sources` records the systems and reports used to build the unified
report. Each entry identifies its source type, collection time, evidence status,
and a non-secret reference to the source report.

Expected future evidence sources include:

* AWS S3 security validator reports.
* Mock Veeam Evidence Report v1 data for backup jobs, repositories, restore
  points, and storage targets.
* Future real Veeam read-only collector reports that preserve the same Veeam
  Evidence Report v1 semantics.
* Microsoft 365 and hybrid workload metadata.
* Restore-test evidence.
* RPO and RTO evaluation results.
* Risk scoring results.
* Runbook and approval metadata.

Evidence collectors should be read-only by default. Missing evidence should be
represented explicitly instead of being silently converted into a negative
finding.

## Asset Model

`assets` is a non-empty list of protected workloads or recovery-relevant
resources. Each asset contains at least:

* `asset_id`: Stable identifier that does not contain a secret.
* `source_type`: Workload or asset source, such as `m365`.
* `backup_system`: Backup platform responsible for the asset, such as `veeam`.
* `risk_score`: Structured deterministic risk result.
* `recommended_action`: Primary reviewable action for the asset.

Assets may include backup-job evidence, RPO/RTO evaluation, immutability
evidence, restore-test evidence, repositories, restore points, storage targets,
and workload metadata.

## Status Semantics

Check-level evidence uses:

* `PASS`: The control or requirement was evaluated and passed.
* `FAIL`: The control or requirement was evaluated and a negative result was
  confirmed.
* `UNKNOWN`: Available evidence is missing or incomplete, including cases where
  contradictory evidence prevents a reliable evaluation.

`UNKNOWN` must never be presented as a confirmed vulnerability.

The unified overall resilience status uses:

* `HEALTHY`: Required evidence and deterministic evaluations indicate expected
  resilience.
* `AT_RISK`: One or more confirmed issues increase resilience risk.
* `INCOMPLETE`: No critical conclusion can be made because required evidence is
  incomplete.
* `CRITICAL`: Confirmed conditions indicate immediate and severe recovery risk.

Overall status calculation rules are intentionally not defined in this initial
contract. They must be introduced later as explicit, deterministic, and tested
policy rules.

## RPO/RTO and Restore-Test Evidence

RPO and RTO results should include the objective, observed value, evaluation
timestamp, status, and reason. They must be calculated by deterministic rules.

Restore-test evidence should record the latest relevant test, result, and source
reference. If no recent test evidence is available, its status is `UNKNOWN`
with a reason such as `NoRecentRestoreTestEvidence`; it is not automatically a
confirmed restore failure.

## Risk Scoring

`risk_score` contains a numeric score, a level, and human-readable rationale.
Scores are prioritization aids based on explicit and reviewable inputs. They
must not independently authorize production changes or recovery actions.

Future versions should define the scoring range, factor weights, policy version,
and treatment of incomplete evidence as a separately tested contract.

## AI/SOAR Relevance

The unified structure enables future AI-assisted summarization, prioritization,
and report drafting across evidence sources. AI output is advisory, not
authoritative, and must preserve source statuses and uncertainty.

Rule-based validators remain authoritative for `PASS`, `FAIL`, and `UNKNOWN`.
Critical actions require deterministic policy checks, versioned runbooks,
least-privilege execution identities, audit logging, and explicit human
approval.

## Future Veeam Read-Only Collector Integration

The `mock_only` profile of `veeam-evidence-report/v1` and local
`veeam_unified_report_adapter` currently populate backup-job, repository,
restore-point, and storage-target evidence without any Veeam API or network
access. The contract-level `api_read_only` profile is intentionally rejected by
the adapter until a later explicit adapter policy is reviewed and implemented.

A future real Veeam API read-only collector is a later step. It should build on
the mock-stabilized evidence semantics, explicitly version real-collection
metadata, use least-privilege read-only permissions, preserve source timestamps
and identifiers, avoid customer secrets in reports, and map missing or
inaccessible evidence to `UNKNOWN` where the evidence remains independently
evaluable.
