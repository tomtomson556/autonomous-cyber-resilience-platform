import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path


POLICY_SCHEMA_VERSION = "rpo-rto-policy/v1"
POLICY_REPORT_TYPE = "rpo_rto_policy"
EVALUATION_SCHEMA_VERSION = "resilience-evaluation-report/v1"
EVALUATION_REPORT_TYPE = "resilience_evaluation_report"
UNIFIED_SCHEMA_VERSION = "1.0.0"
UNIFIED_REPORT_TYPE = "unified_resilience_report"
EVALUATOR_NAME = "deterministic_rpo_rto_evaluator"
EVALUATOR_VERSION = "1"
VALID_UNIFIED_OVERALL_STATUSES = frozenset(
    {"HEALTHY", "INCOMPLETE", "AT_RISK", "CRITICAL"}
)

POLICY_FIELDS = frozenset(
    {"schema_version", "report_type", "evaluation_timestamp", "rules"}
)
REQUIRED_POLICY_FIELDS = frozenset({"schema_version", "report_type", "rules"})
RULE_FIELDS = frozenset(
    {"policy_id", "asset_id", "rpo_objective_minutes", "rto_objective_minutes"}
)
REQUIRED_RULE_FIELDS = frozenset(
    {"policy_id", "asset_id", "rpo_objective_minutes"}
)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _stable_reference(prefix: str, value: object) -> str:
    digest = hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    return f"{prefix}:sha256:{digest}"


def _stable_policy_reference(policy: dict) -> str:
    normalized_policy = {
        **policy,
        "rules": sorted(policy["rules"], key=lambda rule: rule["policy_id"]),
    }
    return _stable_reference("rpo-rto-policy", normalized_policy)


def _require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Field '{field_name}' must be a non-empty string.")
    return value


def _parse_utc_timestamp(value: object, field_name: str) -> datetime:
    timestamp = _require_non_empty_string(value, field_name)
    if not (timestamp.endswith("Z") or timestamp.endswith("+00:00")):
        raise ValueError(f"Field '{field_name}' must be a UTC timestamp.")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"Field '{field_name}' must be valid ISO 8601.") from error
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"Field '{field_name}' must be a UTC timestamp.")
    return parsed


def _positive_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"Field '{field_name}' must be a positive integer.")
    return value


def load_policy(path: Path) -> dict:
    with path.open(encoding="utf-8") as policy_file:
        return json.load(policy_file)


def validate_policy(policy: dict) -> None:
    if not isinstance(policy, dict):
        raise ValueError("RPO/RTO policy must be an object.")
    if set(policy) - POLICY_FIELDS:
        unexpected = sorted(set(policy) - POLICY_FIELDS)
        raise ValueError(f"RPO/RTO policy contains unsupported fields: {unexpected}")
    if not REQUIRED_POLICY_FIELDS <= policy.keys():
        missing = sorted(REQUIRED_POLICY_FIELDS - policy.keys())
        raise ValueError(f"RPO/RTO policy is missing required fields: {missing}")
    if policy["schema_version"] != POLICY_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported RPO/RTO policy schema_version: {policy['schema_version']}"
        )
    if policy["report_type"] != POLICY_REPORT_TYPE:
        raise ValueError(f"RPO/RTO policy report_type must be '{POLICY_REPORT_TYPE}'.")
    if "evaluation_timestamp" in policy:
        _parse_utc_timestamp(policy["evaluation_timestamp"], "evaluation_timestamp")

    rules = policy["rules"]
    if not isinstance(rules, list) or not rules:
        raise ValueError("RPO/RTO policy field 'rules' must be a non-empty list.")

    policy_ids = set()
    asset_ids = set()
    for index, rule in enumerate(rules):
        prefix = f"rules[{index}]"
        if not isinstance(rule, dict):
            raise ValueError(f"Field '{prefix}' must be an object.")
        if set(rule) - RULE_FIELDS:
            unexpected = sorted(set(rule) - RULE_FIELDS)
            raise ValueError(f"Field '{prefix}' contains unsupported fields: {unexpected}")
        if not REQUIRED_RULE_FIELDS <= rule.keys():
            missing = sorted(REQUIRED_RULE_FIELDS - rule.keys())
            raise ValueError(f"Field '{prefix}' is missing required fields: {missing}")

        policy_id = _require_non_empty_string(rule["policy_id"], f"{prefix}.policy_id")
        asset_id = _require_non_empty_string(rule["asset_id"], f"{prefix}.asset_id")
        _positive_integer(
            rule["rpo_objective_minutes"],
            f"{prefix}.rpo_objective_minutes",
        )
        if "rto_objective_minutes" in rule:
            _positive_integer(
                rule["rto_objective_minutes"],
                f"{prefix}.rto_objective_minutes",
            )

        if policy_id in policy_ids:
            raise ValueError(f"Duplicate policy_id: {policy_id}")
        if asset_id in asset_ids:
            raise ValueError(f"Duplicate RPO objective for asset_id: {asset_id}")
        policy_ids.add(policy_id)
        asset_ids.add(asset_id)


def _validate_unified_report(report: dict) -> tuple[dict[str, dict], set[str]]:
    if not isinstance(report, dict):
        raise ValueError("Unified Resilience Report must be an object.")
    if report.get("schema_version") != UNIFIED_SCHEMA_VERSION:
        raise ValueError("Unsupported Unified Resilience Report schema_version.")
    if report.get("report_type") != UNIFIED_REPORT_TYPE:
        raise ValueError(f"Unified report_type must be '{UNIFIED_REPORT_TYPE}'.")
    _parse_utc_timestamp(report.get("timestamp"), "timestamp")
    _require_non_empty_string(report.get("platform"), "platform")
    _require_non_empty_string(report.get("data_classification"), "data_classification")
    if report.get("overall_resilience_status") not in VALID_UNIFIED_OVERALL_STATUSES:
        raise ValueError("Unified report overall_resilience_status is invalid.")

    evidence_sources = report.get("evidence_sources")
    if not isinstance(evidence_sources, list) or not evidence_sources:
        raise ValueError(
            "Unified report field 'evidence_sources' must be a non-empty list."
        )
    evidence_source_ids = set()
    for source in evidence_sources:
        if not isinstance(source, dict):
            raise ValueError("Unified report evidence_sources must be objects.")
        source_id = _require_non_empty_string(
            source.get("source_id"),
            "evidence_sources.source_id",
        )
        if source_id in evidence_source_ids:
            raise ValueError(f"Duplicate Unified source_id: {source_id}")
        evidence_source_ids.add(source_id)
    for collection_name in ("findings", "recommended_actions"):
        if not isinstance(report.get(collection_name), list):
            raise ValueError(f"Unified report field '{collection_name}' must be a list.")

    assets = report.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError("Unified report field 'assets' must be a non-empty list.")

    assets_by_id = {}
    for asset in assets:
        if not isinstance(asset, dict):
            raise ValueError("Unified report assets must be objects.")
        asset_id = _require_non_empty_string(asset.get("asset_id"), "assets.asset_id")
        if asset_id in assets_by_id:
            raise ValueError(f"Duplicate Unified asset_id: {asset_id}")
        assets_by_id[asset_id] = asset
    return assets_by_id, evidence_source_ids


def _direct_backup_evidence(asset: dict) -> list[dict]:
    candidates = []

    backup_job = asset.get("backup_job")
    if isinstance(backup_job, dict):
        source_id = backup_job.get("source_id")
        candidates.append(
            {
                "status": backup_job.get("status"),
                "last_successful_backup": backup_job.get("last_successful_backup"),
                "source_ids": [source_id],
                "requires_source_link": source_id is not None,
            }
        )

    source_evidence = asset.get("source_evidence")
    details = source_evidence.get("details") if isinstance(source_evidence, dict) else None
    if isinstance(details, dict) and (
        asset.get("resource_type") == "backup_job"
        or "last_successful_backup" in details
    ):
        candidates.append(
            {
                "status": source_evidence.get("status"),
                "last_successful_backup": details.get("last_successful_backup"),
                "source_ids": [asset.get("evidence_source_id")],
                "requires_source_link": True,
            }
        )

    return candidates


def _source_ids(candidate: dict) -> list[str]:
    return sorted(
        source_id
        for source_id in candidate["source_ids"]
        if isinstance(source_id, str) and source_id
    )


def _rpo_unknown(
    rule: dict,
    reason: str,
    message: str,
    source_ids: list[str] | None = None,
) -> dict:
    return {
        "objective_type": "RPO",
        "objective_minutes": rule["rpo_objective_minutes"],
        "observed_age_minutes": None,
        "status": "UNKNOWN",
        "reason": reason,
        "message": message,
        "source_evidence_ids": source_ids or [],
    }


def _evaluate_rpo(
    rule: dict,
    assets_by_id: dict[str, dict],
    evidence_source_ids: set[str],
    evaluation_time: datetime,
) -> dict:
    asset = assets_by_id.get(rule["asset_id"])
    if asset is None:
        return _rpo_unknown(
            rule,
            "MISSING_ASSET",
            "The policy asset is not present in the Unified Resilience Report.",
        )

    candidates = _direct_backup_evidence(asset)
    if len(candidates) > 1:
        return _rpo_unknown(
            rule,
            "AMBIGUOUS_BACKUP_EVIDENCE",
            "Multiple directly linked backup evidence candidates prevent evaluation.",
        )
    if not candidates:
        return _rpo_unknown(
            rule,
            "MISSING_BACKUP_EVIDENCE",
            "No trustworthy backup evidence is directly linked to the policy asset.",
        )

    candidate = candidates[0]
    source_ids = _source_ids(candidate)
    if candidate["requires_source_link"] and (
        len(source_ids) != 1 or source_ids[0] not in evidence_source_ids
    ):
        return _rpo_unknown(
            rule,
            "UNLINKED_BACKUP_EVIDENCE",
            "The backup evidence source is not linked to the Unified Report.",
        )
    if candidate["status"] != "PASS":
        return _rpo_unknown(
            rule,
            "MISSING_BACKUP_EVIDENCE",
            "Directly linked backup evidence is not a PASS observation.",
            source_ids,
        )

    backup_timestamp = candidate["last_successful_backup"]
    if not isinstance(backup_timestamp, str) or not backup_timestamp:
        return _rpo_unknown(
            rule,
            "MISSING_BACKUP_EVIDENCE",
            "Directly linked backup evidence has no last-successful-backup timestamp.",
            source_ids,
        )
    try:
        datetime.fromisoformat(backup_timestamp.replace("Z", "+00:00"))
    except ValueError:
        return _rpo_unknown(
            rule,
            "INVALID_BACKUP_TIMESTAMP",
            "The last-successful-backup timestamp is malformed.",
            source_ids,
        )
    if not (
        backup_timestamp.endswith("Z") or backup_timestamp.endswith("+00:00")
    ):
        return _rpo_unknown(
            rule,
            "NON_UTC_BACKUP_TIMESTAMP",
            "The last-successful-backup timestamp is not UTC.",
            source_ids,
        )
    try:
        backup_time = _parse_utc_timestamp(
            backup_timestamp,
            "last_successful_backup",
        )
    except ValueError:
        return _rpo_unknown(
            rule,
            "INVALID_BACKUP_TIMESTAMP",
            "The last-successful-backup timestamp is malformed.",
            source_ids,
        )
    if backup_time > evaluation_time:
        return _rpo_unknown(
            rule,
            "FUTURE_BACKUP_TIMESTAMP",
            "The last-successful-backup timestamp is after the evaluation timestamp.",
            source_ids,
        )

    observed_age_minutes = (evaluation_time - backup_time).total_seconds() / 60
    objective = rule["rpo_objective_minutes"]
    if observed_age_minutes <= objective:
        return {
            "objective_type": "RPO",
            "objective_minutes": objective,
            "observed_age_minutes": observed_age_minutes,
            "status": "PASS",
            "reason": "RPO_WITHIN_OBJECTIVE",
            "message": "The directly linked successful backup is within the RPO objective.",
            "source_evidence_ids": source_ids,
        }
    return {
        "objective_type": "RPO",
        "objective_minutes": objective,
        "observed_age_minutes": observed_age_minutes,
        "status": "FAIL",
        "reason": "RPO_EXCEEDED",
        "message": "The directly linked successful backup exceeds the RPO objective.",
        "source_evidence_ids": source_ids,
    }


def _evaluate_rto(rule: dict) -> dict:
    return {
        "objective_type": "RTO",
        "objective_minutes": rule["rto_objective_minutes"],
        "observed_recovery_minutes": None,
        "status": "UNKNOWN",
        "reason": "RTO_EVIDENCE_CONTRACT_NOT_AVAILABLE",
        "message": (
            "RTO cannot be evaluated until a separate versioned restore-test "
            "evidence contract exists."
        ),
        "source_evidence_ids": [],
    }


def _evaluation_id(
    input_reference: str,
    policy_reference: str,
    policy_id: str,
    asset_id: str,
    evaluation_timestamp: str,
    result: dict,
) -> str:
    stable_inputs = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "input_report_reference": input_reference,
        "policy_reference": policy_reference,
        "policy_id": policy_id,
        "asset_id": asset_id,
        "objective_type": result["objective_type"],
        "evaluation_timestamp": evaluation_timestamp,
        "status": result["status"],
        "reason": result["reason"],
    }
    digest = hashlib.sha256(_canonical_json(stable_inputs).encode("utf-8")).hexdigest()
    return f"evaluation-{digest[:20]}"


def evaluate_report(
    report: dict,
    policy: dict,
    evaluation_timestamp: str | None = None,
) -> dict:
    validate_policy(policy)
    assets_by_id, evidence_source_ids = _validate_unified_report(report)

    effective_timestamp = (
        evaluation_timestamp
        if evaluation_timestamp is not None
        else policy.get("evaluation_timestamp")
    )
    if effective_timestamp is None:
        raise ValueError("An explicit evaluation timestamp is required.")
    evaluation_time = _parse_utc_timestamp(
        effective_timestamp,
        "evaluation_timestamp",
    )

    input_reference = _stable_reference("unified-report", report)
    policy_reference = _stable_policy_reference(policy)
    asset_results = []
    for rule in sorted(policy["rules"], key=lambda item: item["asset_id"]):
        evaluations = [
            _evaluate_rpo(
                rule,
                assets_by_id,
                evidence_source_ids,
                evaluation_time,
            )
        ]
        if "rto_objective_minutes" in rule:
            evaluations.append(_evaluate_rto(rule))
        for result in evaluations:
            result["evaluation_id"] = _evaluation_id(
                input_reference,
                policy_reference,
                rule["policy_id"],
                rule["asset_id"],
                effective_timestamp,
                result,
            )
        evaluations.sort(key=lambda item: item["objective_type"])
        asset_results.append(
            {
                "asset_id": rule["asset_id"],
                "policy_id": rule["policy_id"],
                "evaluations": evaluations,
            }
        )

    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "report_type": EVALUATION_REPORT_TYPE,
        "evaluation_timestamp": effective_timestamp,
        "evaluator": {
            "name": EVALUATOR_NAME,
            "version": EVALUATOR_VERSION,
            "mode": "deterministic_local_policy_evaluation",
        },
        "input_unified_report": {
            "reference": input_reference,
            "schema_version": report["schema_version"],
            "report_type": report["report_type"],
        },
        "policy": {
            "reference": policy_reference,
            "schema_version": policy["schema_version"],
            "report_type": policy["report_type"],
        },
        "asset_results": asset_results,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate local Unified Resilience Reports against RPO/RTO policy."
    )
    parser.add_argument("input", type=Path, help="Unified Resilience Report JSON path.")
    parser.add_argument("--policy", required=True, type=Path, help="Policy JSON path.")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON path.")
    parser.add_argument(
        "--evaluation-timestamp",
        help="Explicit UTC evaluation timestamp overriding the policy timestamp.",
    )
    return parser.parse_args(argv)


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as json_file:
        return json.load(json_file)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        resolved_output = args.output.resolve()
        if resolved_output in {args.input.resolve(), args.policy.resolve()}:
            raise ValueError("Output path must differ from input and policy paths.")
        if args.output.exists():
            raise ValueError(f"Output path already exists: {args.output}")

        report = _load_json(args.input)
        policy = load_policy(args.policy)
        evaluation = evaluate_report(
            report,
            policy,
            args.evaluation_timestamp,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as output_file:
            json.dump(evaluation, output_file, indent=2, sort_keys=True)
            output_file.write("\n")
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"RPO/RTO evaluation failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
