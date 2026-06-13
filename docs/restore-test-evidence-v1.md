# Restore-Test Evidence v1

## Purpose

`restore-test-evidence/v1` is a local, versioned evidence contract for recording
the outcome of restore tests that were performed outside this repository. The
contract and validator do not start, control, retry, or otherwise execute a
restore. They only validate sanitized local JSON evidence.

Restore-test evidence is distinct from:

* Backup evidence, which can show that a backup operation completed.
* Restore points, which can show that a recovery point exists.
* RPO evaluation, which measures the age of trustworthy backup evidence.

A successful backup or an existing restore point does not prove that data can
be restored, validated, or recovered within an objective. The local
`rpo_rto_evaluator` may optionally use this validated contract for deterministic
RTO evaluation; without a unique, trustworthy match, RTO remains `UNKNOWN`.

## Contract Identity

Every report has:

```json
{
  "schema_version": "restore-test-evidence/v1",
  "report_type": "restore_test_evidence_report"
}
```

The validator accepts only the exact documented fields. Unexpected connection,
authentication, credential, secret, or external-service configuration fields
are rejected.

## Allowed Data Sources

The top-level `source.source_type` allows:

* `sanitized_fixture`: deterministic local test data.
* `manual_attestation`: a locally prepared, reviewable evidence record.
* `external_test_record`: a sanitized record exported by a separately operated
  restore-test process and then imported locally.

Each restore-test provenance `collection_method` allows:

* `sanitized_fixture`
* `manual_import`
* `external_record_import`

Each restore-test `validation.method` is the report's source type:

* `sanitized_fixture`
* `manual_attestation`
* `external_test_record`

Source profiles are fixed:

* `sanitized_fixture` requires `MOCK_EXAMPLE_ONLY` and `sanitized_fixture`.
* `manual_attestation` requires `SANITIZED_OPERATIONAL_EVIDENCE` and
  `manual_import`.
* `external_test_record` requires `SANITIZED_OPERATIONAL_EVIDENCE` and
  `external_record_import`.

The contract does not allow direct API collection, productive endpoints, raw
responses, credentials, tokens, internal URLs, hostnames, or connection
settings. Source identifiers and references must be sanitized local references,
not URLs, hostnames, paths, or connection strings. Sanitized references use
only letters, numbers, `:`, `_`, and `-`.

The validator enforces the closed structure, source profiles, and sanitized
reference syntax. It cannot prove that arbitrary human-readable `reason` or
`message` text contains no sensitive data. Evidence producers must sanitize
free text before creating a report. Shipped fixtures contain no real customer
data, secrets, tokens, hostnames, or productive identifiers.

## Report Structure

Every report contains exactly:

* `schema_version`: Must be `restore-test-evidence/v1`.
* `report_type`: Must be `restore_test_evidence_report`.
* `generated_at`: Strict UTC timestamp using `Z` or `+00:00`.
* `source`: Source identifier and allowed source type.
* `data_classification`: `MOCK_EXAMPLE_ONLY` or
  `SANITIZED_OPERATIONAL_EVIDENCE`.
* `restore_tests`: Non-empty list of restore-test evidence.

Version 1 defines no optional report, source, restore-test, validation, or
provenance fields. Timing fields are required keys but may all be `null` only
for incomplete `UNKNOWN` evidence. Validation fields are required keys; only
`UNKNOWN` evidence may use `null` for `validation.checked_at` or
`validation.evidence_reference`.

The source object contains exactly:

* `source_id`: Sanitized stable local identifier.
* `source_type`: One allowed source type.

## Restore-Test Structure

Every restore-test entry contains exactly:

* `restore_test_id`: Unique sanitized identifier.
* `asset_id`: Explicit identifier of the tested asset.
* `source_system`: Sanitized identifier of the source backup system.
* `source_backup_reference`: Sanitized reference to the tested backup.
* `restore_scope`: `full_asset`, `partial_asset`, or `item_level`.
* `restore_target_type`: `isolated_test_environment`, `sandbox`, or
  `alternate_non_production_location`.
* `started_at`: Strict UTC timestamp or `null` for incomplete `UNKNOWN`
  evidence.
* `completed_at`: Strict UTC timestamp or `null` for incomplete `UNKNOWN`
  evidence.
* `duration_seconds`: Non-negative integer matching the timestamps, or `null`
  for incomplete `UNKNOWN` evidence.
* `result`: `PASS`, `FAIL`, or `UNKNOWN`.
* `reason`: Non-empty deterministic reason.
* `message`: Non-empty human-readable explanation.
* `validation`: Exact structured validation attestation.
* `provenance`: Exact source-record provenance.

Validation contains exactly:

* `method`: Must equal the report's `source.source_type`.
* `status`: `VERIFIED`, `FAILED`, or `UNKNOWN`, with the result mapping defined
  below.
* `checked_at`: Strict UTC timestamp, or `null` only for `UNKNOWN`.
* `evidence_reference`: Sanitized stable local reference to the validation
  record, or `null` only for `UNKNOWN`.

Provenance contains exactly:

* `source_record_id`: Sanitized stable local identifier.
* `collected_at`: Strict UTC timestamp.
* `collection_method`: One allowed local collection method.

`restore_test_id` values must be unique. The tuple
`(source.source_id, provenance.source_record_id)` is also unique within a
report, preventing one source record from being represented as multiple
restore tests. Restore-test entries are returned in deterministic
`restore_test_id` order. Input objects are not mutated.

## Result Semantics

* `PASS`: A complete restore test finished and the source attested its
  structured validation as `VERIFIED`.
* `FAIL`: A complete restore test finished and the source attested its
  structured validation as `FAILED`.
* `UNKNOWN`: Available evidence cannot support a reliable pass or fail
  conclusion, and structured validation is `UNKNOWN`.

`PASS` and `FAIL` require complete, internally consistent timing. `UNKNOWN` may
contain complete timing when the outcome remains inconclusive, or all timing
fields may be `null` when timing evidence is unavailable. Partially populated
timing is rejected.

For every entry, `provenance.collected_at` must not be after `generated_at`.
When completion and validation timestamps exist, the complete ordering is
`started_at <= completed_at <= validation.checked_at <=
provenance.collected_at <= generated_at`.

Free-text `reason` and `message` explain the outcome but are never sufficient
validation evidence and are never used to derive `result`. All non-empty
strings reject whitespace-only values. Validation evidence references use the
same sanitized local-reference restrictions as other references and cannot be
URLs, paths, hostnames, connection strings, secrets, tokens, credentials, or
raw API data.

`UNKNOWN` is never treated as a confirmed restore failure. This contract does
not convert any result into an RTO conclusion.

The evaluator retains `RTO_EVIDENCE_CONTRACT_NOT_AVAILABLE` when no
restore-test evidence input is supplied. When supplied, only structured fields
from a fully validated report are used. A documented restore test is evidence
of that test record, not a guarantee of current live-restore capability.

## Examples

Complete sanitized examples are shipped under
`tests/fixtures/restore_test_evidence/`.

### PASS

```json
{
  "restore_test_id": "restore-test-pass-001",
  "asset_id": "asset-example-001",
  "source_system": "example-backup-system",
  "source_backup_reference": "backup-example-001",
  "restore_scope": "full_asset",
  "restore_target_type": "isolated_test_environment",
  "started_at": "2026-06-12T12:00:00+00:00",
  "completed_at": "2026-06-12T12:10:00+00:00",
  "duration_seconds": 600,
  "result": "PASS",
  "reason": "RestoreCompletedAndValidated",
  "message": "The sanitized restore test completed and validation passed.",
  "validation": {
    "method": "sanitized_fixture",
    "status": "VERIFIED",
    "checked_at": "2026-06-12T12:15:00+00:00",
    "evidence_reference": "fixture-validation-pass-001"
  },
  "provenance": {
    "source_record_id": "fixture-record-pass-001",
    "collected_at": "2026-06-12T12:20:00+00:00",
    "collection_method": "sanitized_fixture"
  }
}
```

### FAIL

```json
{
  "result": "FAIL",
  "reason": "RestoreValidationFailed",
  "message": "The restore completed but its defined validation failed.",
  "validation": {
    "method": "sanitized_fixture",
    "status": "FAILED",
    "checked_at": "2026-06-12T12:10:00Z",
    "evidence_reference": "fixture-validation-fail-001"
  }
}
```

The remaining required fields and complete consistent timing are still
required.

### UNKNOWN

```json
{
  "started_at": null,
  "completed_at": null,
  "duration_seconds": null,
  "result": "UNKNOWN",
  "reason": "RestoreTestEvidenceIncomplete",
  "message": "The local record does not contain complete restore-test evidence.",
  "validation": {
    "method": "sanitized_fixture",
    "status": "UNKNOWN",
    "checked_at": null,
    "evidence_reference": null
  }
}
```

The remaining required identity, scope, target, and provenance fields are still
required.

## Local Validation

```python
from pathlib import Path

from src.tools.restore_test_evidence import load_restore_test_evidence

report = load_restore_test_evidence(Path("restore-test-evidence.json"))
```

Validation is deterministic and local. It adds no productive HTTP client,
network access, Veeam authentication, logon, session handling, TLS or
certificate logic, secret provider, credentials, restore execution, write,
mutation, delete, job-control behavior, direct API-to-Unified shortcut, or risk
scoring.
