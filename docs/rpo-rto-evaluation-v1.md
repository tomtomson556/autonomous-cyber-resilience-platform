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

## Deferred RTO Semantics

Version 1 performs no real RTO evaluation. If a policy contains an RTO
objective, the result is always `UNKNOWN` with reason
`RTO_EVIDENCE_CONTRACT_NOT_AVAILABLE`.

Backup existence, successful backup sessions, restore-point existence, and RPO
success do not prove recoverability or RTO compliance. Arbitrary
restore-test-looking fields are deliberately ignored until a separate
versioned restore-test evidence contract exists.

## Evaluation Report Contract

The output schema version is `resilience-evaluation-report/v1` and its report
type is `resilience_evaluation_report`. It contains:

* The explicit evaluation timestamp.
* Deterministic evaluator identity and version.
* Stable references to the input Unified Report and policy.
* Stable, asset-sorted policy results.
* Deterministic evaluation IDs.
* RPO and optional deferred RTO results with status, reason, message, objective,
  observed value where available, and source evidence identifiers where
  applicable.

The output contains only derived evaluation results. It does not copy the
Unified Report, create collector evidence, change Unified findings, or alter
the Unified overall status.

## CLI

```bash
python -m src.tools.rpo_rto_evaluator \
  INPUT \
  --policy POLICY \
  --output OUTPUT \
  --evaluation-timestamp 2026-06-12T12:00:00+00:00
```

The CLI reads and writes local JSON only, fails closed on invalid contracts,
does not overwrite an existing output, and refuses to use the input or policy
path as output.

The evaluator adds no external API access, productive transport,
authentication, TLS or certificate handling, credentials, secrets, restore,
write, mutation, delete, or job-control behavior.
