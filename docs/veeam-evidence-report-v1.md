# Veeam Evidence Report v1

## Purpose

The Veeam Evidence Report v1 contract defines deterministic evidence for backup
jobs, repositories, restore points, and storage targets. The shipped example
and current Unified Resilience Report mapping remain mock-only. The contract
also reserves an explicit `api_read_only` profile for a later real collector.

The schema version is:

```text
veeam-evidence-report/v1
```

The current implementation contains no credentials, endpoints, SDK clients,
network calls, or production-changing behavior.

## Report Shape

Every report contains:

* `schema_version`
* `timestamp`
* `report_type`
* `data_classification`
* `collector`
* `overall_status`
* `backup_jobs`
* `repositories`
* `restore_points`
* `storage_targets`

## Collector Profiles

The contract recognizes exactly two collector modes:

* `mock_only`
* `api_read_only`

The shipped example uses the current default `mock_only` profile:

```json
{
  "data_classification": "MOCK_EXAMPLE_ONLY",
  "collector": {
    "name": "mock_veeam_evidence_collector",
    "mode": "mock_only"
  }
}
```

The reserved `api_read_only` profile identifies sanitized operational evidence
that a future collector may obtain from Veeam Backup Enterprise Manager REST
API read endpoints:

```json
{
  "data_classification": "SANITIZED_OPERATIONAL_EVIDENCE",
  "collector": {
    "name": "veeam_enterprise_manager_read_only_collector",
    "mode": "api_read_only"
  }
}
```

`api_read_only` reports are not mock data. They must not contain secrets,
tokens, internal URLs, credentials, or raw API response dumps. The current
Unified Resilience Report adapter rejects this profile until a later explicit
adapter policy is reviewed and implemented.

## Resource Collections

Required mock resource fields are:

* `backup_jobs`: `job_id`, `job_name`, `workload_type`, `repository_id`,
  `last_successful_backup`, and `evidence`.
* `repositories`: `repository_id`, `repository_name`, `storage_target_id`, and
  `evidence`.
* `restore_points`: `restore_point_id`, `job_id`, `created_at`, and `evidence`.
* `storage_targets`: `storage_target_id`, `target_type`, and `evidence`.

Required identifiers and resource fields are non-empty strings. Every resource
identifier must be unique within the report.

## Evidence Status Semantics

Each resource contains a structured `evidence` result:

```json
{
  "status": "PASS|FAIL|UNKNOWN",
  "reason": "optional reason",
  "message": "human-readable evidence explanation"
}
```

* `PASS` means the available evidence confirms the expected condition.
* `FAIL` means the available evidence confirms a negative condition.
* `UNKNOWN` means the evidence is incomplete or not trustworthy enough to
  decide.

The deterministic overall status is:

* `HEALTHY`: every resource evidence result is `PASS`.
* `AT_RISK`: at least one resource evidence result is `FAIL`.
* `INCOMPLETE`: no result is `FAIL`, but at least one result is `UNKNOWN`.

`AT_RISK` takes precedence over `INCOMPLETE`.

## Unified Report Adapter

The local `veeam_unified_report_adapter` accepts only the `mock_only` profile of
`veeam-evidence-report/v1`. It maps every mock Veeam evidence resource to a
Unified Resilience Report asset and creates findings for `FAIL` and `UNKNOWN`
evidence.

The adapter preserves status, reason, message, collection timestamp, source
schema version, mock collector identity, and evidence origin. It performs no
risk scoring and creates no recommendations or actions.

## Network-Free Read-Only Collector Groundwork

The current `api_read_only` collector is network-free groundwork with an
injectable transport interface. It contains no productive HTTP,
authentication, TLS, credential, or session implementation. Tests use only a
fake transport and sanitized fake responses.

The collector accepts exactly these requests:

* `GET /backups`
* `GET /backupSessions`
* `GET /restorePoints`
* `GET /query?type=Repository`

Every other method, path, or query combination is blocked before the transport
is called. This includes all restore, start, stop, retry, delete, action, and
mutation paths. `GET /jobs` is deliberately not allowed.

The collector produces only `veeam-evidence-report/v1` with the
`api_read_only` profile. It does not call the Unified Resilience Report adapter,
and that adapter continues to reject `api_read_only` reports.

`backup_jobs` and `storage_targets` remain empty in this step. Sessions are not
emitted as v1 resources. Repository and restore-point entries are emitted only
when every required identifier and relationship is present in the sanitized
response. Incomplete entries are omitted rather than completed with invented
values, and the report remains `INCOMPLETE`. Read-only observations are
represented as `UNKNOWN`; their presence alone does not prove a resilience
condition.

## Future Network Integration Boundary

A future productive client must preserve the strict allowlist, keep TLS
certificate verification enabled by default, read secrets only from runtime
secret providers, and never emit secrets, internal endpoints, or raw API
responses. Authentication and any expansion of the endpoint allowlist require
a separate explicit design decision and review.
