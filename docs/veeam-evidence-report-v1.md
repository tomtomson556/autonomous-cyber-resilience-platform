# Veeam Evidence Report v1

## Purpose

The Veeam Evidence Report v1 contract defines deterministic, mock-only evidence
for backup jobs, repositories, restore points, and storage targets. It proves
the source contract and Unified Resilience Report mapping before any real Veeam
API collector is implemented.

The schema version is:

```text
veeam-evidence-report/v1
```

This contract contains no credentials, endpoints, SDK clients, network calls,
or production-changing behavior.

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

The mock collector metadata must identify `mode` as `mock_only`.

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

* `PASS` means the available mock evidence confirms the expected condition.
* `FAIL` means the available mock evidence confirms a negative condition.
* `UNKNOWN` means the evidence is incomplete or not trustworthy enough to
  decide.

The deterministic overall status is:

* `HEALTHY`: every resource evidence result is `PASS`.
* `AT_RISK`: at least one resource evidence result is `FAIL`.
* `INCOMPLETE`: no result is `FAIL`, but at least one result is `UNKNOWN`.

`AT_RISK` takes precedence over `INCOMPLETE`.

## Unified Report Adapter

The local `veeam_unified_report_adapter` accepts only
`veeam-evidence-report/v1`. It maps every Veeam evidence resource to a Unified
Resilience Report asset and creates findings for `FAIL` and `UNKNOWN` evidence.

The adapter preserves status, reason, message, collection timestamp, source
schema version, mock collector identity, and evidence origin. It performs no
risk scoring and creates no recommendations or actions.

## Real Collector Boundary

A real Veeam read-only collector is a later step. It should build on these
stabilized status semantics and explicitly version real-collection metadata.
Real API access, credentials, endpoints, and authentication are intentionally
outside the v1 mock contract.
