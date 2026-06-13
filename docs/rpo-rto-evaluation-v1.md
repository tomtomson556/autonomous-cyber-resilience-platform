# Deterministic RPO/RTO Evaluation v1

## Purpose

The local `rpo_rto_evaluator` is a separate deterministic policy layer. It
consumes one existing Unified Resilience Report and one local policy, then
produces a separate evaluation report. It does not modify the Unified Report or
change its global status.

The layer boundaries remain:

* Collectors observe source systems.
* Adapters normalize observed evidence.
* The composer combines existing Unified Reports.
* The evaluator applies explicit deterministic policy.

Evaluation results are derived policy conclusions. They are not
collector-observed facts and are not added back into the input evidence.

## Policy Contract

The policy schema version is `rpo-rto-policy/v1` and its report type is
`rpo_rto_policy`.

```json
{
  "schema_version": "rpo-rto-policy/v1",
  "report_type": "rpo_rto_policy",
  "evaluation_timestamp": "2026-06-12T12:00:00+00:00",
  "rules": [
    {
      "policy_id": "example-backup-job-policy",
      "asset_id": "veeam-backup_job:example-job",
      "rpo_objective_minutes": 1440,
      "rto_objective_minutes": 480
    }
  ]
}
```

Every rule has exactly one positive RPO objective and may have one positive RTO
objective. Policy and asset identifiers must be unique. Unsupported fields are
rejected, which also prevents connection, authentication, credential, secret,
or external-service configuration from entering this local policy contract.

The evaluation timestamp is supplied by CLI override first, then by policy. It
must be explicit UTC using `Z` or `+00:00`; the evaluator never reads the wall
clock.

## RPO Semantics

RPO is evaluated only from one directly linked backup evidence object on the
policy asset. The evidence must be `PASS` and expose one valid UTC
`last_successful_backup` timestamp at or before the evaluation timestamp.

The exact boundary is:

* `PASS`: observed backup age is less than or equal to the objective.
* `FAIL`: observed backup age exceeds the objective.
* `UNKNOWN`: the asset or trustworthy direct evidence is missing, invalid,
  ambiguous, unlinked, incomplete, or future-dated.

`UNKNOWN` is never converted into `FAIL`. Evidence on another asset is not
implicitly correlated with the policy asset.

## RTO Semantics

Version 1 optionally accepts one validated local `restore-test-evidence/v1`
report. Evidence is matched only by exact `asset_id`. Arbitrary
restore-test-looking Unified fields and free-text evidence fields are ignored.

Without a restore-test evidence input, configured RTO results preserve the
compatible `UNKNOWN` result and `RTO_EVIDENCE_CONTRACT_NOT_AVAILABLE` reason.
With validated evidence:

* No exact asset match produces `RTO_RESTORE_TEST_ASSET_NOT_FOUND`.
* Multiple reliable exact matches produce `RTO_RESTORE_TEST_AMBIGUOUS`.
* Structured `UNKNOWN` produces `RTO_RESTORE_TEST_UNKNOWN`.
* Any relevant timestamp after the evaluation timestamp produces
  `RTO_RESTORE_TEST_FUTURE_TIMESTAMP`.
* Structured `FAIL` produces `RTO_RESTORE_TEST_FAILED`, independently of its
  duration.
* Structured `PASS` produces `RTO_WITHIN_OBJECTIVE` when
  `duration_seconds <= rto_objective_minutes * 60`; otherwise it produces
  `RTO_EXCEEDED_OBJECTIVE`.

`observed_recovery_minutes` is derived from `duration_seconds / 60` for
structured `PASS` and `FAIL` evidence. No evidence-age rule is applied because
`rpo-rto-policy/v1` defines no maximum acceptable restore-test age.

Backup existence, successful backup sessions, restore-point existence, and RPO
success do not prove recoverability or RTO compliance. A documented restore
test supports evaluation of that test record, but it is not a guarantee of
current live-restore capability.

## Evaluation Report Contract

The output schema version is `resilience-evaluation-report/v1` and its report
type is `resilience_evaluation_report`. It contains:

* The explicit evaluation timestamp.
* Deterministic evaluator identity and version.
* Stable references to the input Unified Report and policy.
* Stable, asset-sorted policy results.
* Deterministic evaluation IDs.
* RPO and optional RTO results with status, reason, message, objective,
  observed value where available, and source evidence identifiers where
  applicable.
* An optional stable restore-test input reference when that input is supplied.
* A stable `restore_test_id` on RTO results when one exact evidence entry is
  evaluated.

The output contains only derived evaluation results. It does not copy the
Unified Report, create collector evidence, change Unified findings, or alter
the Unified overall status. The optional restore-test input reference and
`restore_test_id` are additive fields in `resilience-evaluation-report/v1`;
existing RPO result fields and behavior remain unchanged.

## CLI

```bash
python -m src.tools.rpo_rto_evaluator \
  INPUT \
  --policy POLICY \
  --restore-test-evidence RESTORE_TEST_EVIDENCE \
  --output OUTPUT \
  --evaluation-timestamp 2026-06-12T12:00:00+00:00
```

`--restore-test-evidence` is optional and accepts exactly one local
`restore-test-evidence/v1` JSON file. Invalid restore-test evidence fails closed
and produces no evaluation report.

The CLI reads and writes local JSON only, fails closed on invalid contracts,
does not overwrite an existing output, and refuses to use the input or policy
path, or restore-test evidence path, as output.

The evaluator adds no external API access, productive transport,
authentication, TLS or certificate handling, credentials, secrets, restore,
write, mutation, delete, or job-control behavior.
