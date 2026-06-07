# Security Check Status Model

## Purpose

This status model separates confirmed security findings from missing or
incomplete evidence. It provides a consistent foundation for reports,
automation, and future AI orchestration.

## Check-level statuses

Each completed security check has one of these statuses:

* `PASS`: The control was evaluated and is configured correctly.
* `FAIL`: The control was evaluated and is insecure or incorrectly configured.
* `UNKNOWN`: The control could not be evaluated with sufficient confidence.

`UNKNOWN` may result from an `AccessDenied` response for an individual check,
missing evidence, or an incomplete service response.

## Overall status calculation

The overall status is calculated from all check-level statuses:

* `SECURE`: Every check is `PASS`.
* `INSECURE`: At least one check is `FAIL`.
* `INCOMPLETE`: No check is `FAIL`, but at least one check is `UNKNOWN`.

`INSECURE` takes precedence over `INCOMPLETE`. An empty or invalid set of check
statuses cannot produce an overall status.

## Difference between `FAIL` and `UNKNOWN`

`FAIL` is a confirmed negative security finding. The check completed and found
that the control is missing, insecure, or incorrectly configured.

`UNKNOWN` means that the available evidence is insufficient to determine
whether the control passes or fails. Missing evidence must not be interpreted
as a confirmed security issue.

## Execution errors versus check results

Check results describe individual security controls. Runtime and execution
errors describe failures that prevent reliable validation as a whole.

Hard execution failures must not be hidden as individual `UNKNOWN` results.
Examples include:

* The target bucket does not exist.
* AWS credentials are missing or invalid.
* AWS client, network, or endpoint communication fails.
* Validation cannot start or cannot identify the intended target.

These conditions remain runtime or execution errors. An `AccessDenied` response
for one optional or independently evaluable control should instead become an
`UNKNOWN` result for that check.

## Examples

All controls pass:

```json
{
  "checks": ["PASS", "PASS", "PASS"],
  "overall_status": "SECURE"
}
```

One confirmed security issue:

```json
{
  "checks": ["PASS", "UNKNOWN", "FAIL"],
  "overall_status": "INSECURE"
}
```

Incomplete evidence without a confirmed failure:

```json
{
  "checks": ["PASS", "UNKNOWN", "PASS"],
  "overall_status": "INCOMPLETE"
}
```

## Relevance for future AI orchestration

Future AI orchestration may analyze, prioritize, and explain check results, but
it must preserve their meaning. AI must treat `UNKNOWN` only as missing or
incomplete evidence and must not present it as a confirmed vulnerability.

Recommendations based on `UNKNOWN` should request additional evidence or
review. Productive changes remain controlled by fixed rules, reviews, and
explicit approvals.
