import argparse
import hashlib
import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path


UNIFIED_SCHEMA_VERSION = "1.0.0"
UNIFIED_REPORT_TYPE = "unified_resilience_report"
COMPOSER_NAME = "unified_report_composer"

VALID_OVERALL_STATUSES = frozenset(
    {"HEALTHY", "INCOMPLETE", "AT_RISK", "CRITICAL"}
)
VALID_FINDING_STATUSES = frozenset({"PASS", "FAIL", "UNKNOWN"})
STATUS_PRIORITY = {
    "HEALTHY": 0,
    "INCOMPLETE": 1,
    "AT_RISK": 2,
    "CRITICAL": 3,
}


def _require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Unified report field '{field_name}' must be a non-empty string.")
    return value


def _parse_timestamp(value: object) -> datetime:
    timestamp = _require_non_empty_string(value, "timestamp")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Unified report timestamp must be valid ISO 8601.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Unified report timestamp must include a UTC offset.")
    return parsed


def _require_list(report: dict, field_name: str, *, non_empty: bool = False) -> list:
    value = report.get(field_name)
    if not isinstance(value, list) or (non_empty and not value):
        requirement = "a non-empty list" if non_empty else "a list"
        raise ValueError(f"Unified report field '{field_name}' must be {requirement}.")
    return value


def _validate_identified_entries(
    entries: list,
    collection_name: str,
    id_field: str,
) -> list[str]:
    identifiers = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"Unified report field '{collection_name}' must contain objects.")
        identifiers.append(
            _require_non_empty_string(
                entry.get(id_field),
                f"{collection_name}.{id_field}",
            )
        )
    return identifiers


def _validate_findings(findings: list) -> list[str]:
    finding_ids = _validate_identified_entries(findings, "findings", "finding_id")
    for finding in findings:
        status = finding.get("status")
        if status not in VALID_FINDING_STATUSES:
            raise ValueError(f"Unified finding '{finding['finding_id']}' status is invalid.")
        confirmed = finding.get("confirmed_vulnerability")
        if not isinstance(confirmed, bool):
            raise ValueError(
                f"Unified finding '{finding['finding_id']}' "
                "confirmed_vulnerability must be a boolean."
            )
        if status == "UNKNOWN" and confirmed:
            raise ValueError(
                f"Unified finding '{finding['finding_id']}' cannot confirm UNKNOWN evidence."
            )
    return finding_ids


def _validate_recommended_actions(actions: list) -> list[str]:
    action_ids = []
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("Unified report field 'recommended_actions' must contain objects.")
        if "action_id" in action:
            action_ids.append(
                _require_non_empty_string(
                    action["action_id"],
                    "recommended_actions.action_id",
                )
            )
    return action_ids


def _validate_report(report: object) -> dict:
    if not isinstance(report, dict):
        raise ValueError("Unified report must be an object.")

    schema_version = report.get("schema_version")
    if schema_version is None:
        raise ValueError("Unified report schema_version is required.")
    if schema_version != UNIFIED_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported Unified report schema_version: {schema_version}"
        )

    if report.get("report_type") != UNIFIED_REPORT_TYPE:
        raise ValueError(
            f"Unified report_type must be '{UNIFIED_REPORT_TYPE}'."
        )

    parsed_timestamp = _parse_timestamp(report.get("timestamp"))
    platform = _require_non_empty_string(report.get("platform"), "platform")
    data_classification = _require_non_empty_string(
        report.get("data_classification"),
        "data_classification",
    )

    overall_status = report.get("overall_resilience_status")
    if overall_status not in VALID_OVERALL_STATUSES:
        raise ValueError("Unified report overall_resilience_status is invalid.")

    evidence_sources = _require_list(report, "evidence_sources", non_empty=True)
    assets = _require_list(report, "assets", non_empty=True)
    findings = _require_list(report, "findings")
    recommended_actions = _require_list(report, "recommended_actions")

    return {
        "report": report,
        "parsed_timestamp": parsed_timestamp,
        "platform": platform,
        "data_classification": data_classification,
        "overall_status": overall_status,
        "source_ids": _validate_identified_entries(
            evidence_sources,
            "evidence_sources",
            "source_id",
        ),
        "asset_ids": _validate_identified_entries(assets, "assets", "asset_id"),
        "finding_ids": _validate_findings(findings),
        "action_ids": _validate_recommended_actions(recommended_actions),
    }


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _stable_report_identifier(report: dict) -> str:
    digest = hashlib.sha256(_canonical_json(report).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _reject_duplicates(identifiers: list[str], identifier_name: str) -> None:
    seen = set()
    for identifier in identifiers:
        if identifier in seen:
            raise ValueError(f"Duplicate {identifier_name}: {identifier}")
        seen.add(identifier)


def _finding_status(finding: dict) -> str:
    if finding["status"] == "FAIL" or finding["confirmed_vulnerability"]:
        return "AT_RISK"
    if finding["status"] == "UNKNOWN":
        return "INCOMPLETE"
    return "HEALTHY"


def compose_unified_reports(
    reports: list[dict],
    input_identifiers: list[str] | None = None,
) -> dict:
    if not isinstance(reports, list) or len(reports) < 2:
        raise ValueError("At least two Unified Resilience Reports are required.")

    validated_reports = [_validate_report(report) for report in reports]
    if input_identifiers is None:
        identifiers = [_stable_report_identifier(report) for report in reports]
    else:
        if len(input_identifiers) != len(reports):
            raise ValueError("Input identifiers must match the number of reports.")
        identifiers = [
            _require_non_empty_string(identifier, "input_identifier")
            for identifier in input_identifiers
        ]
    _reject_duplicates(identifiers, "input identifier")

    platforms = {validated["platform"] for validated in validated_reports}
    if len(platforms) != 1:
        raise ValueError("Unified reports must use the same platform.")

    data_classifications = {
        validated["data_classification"] for validated in validated_reports
    }
    if len(data_classifications) != 1:
        raise ValueError("Unified reports must use the same data_classification.")

    all_source_ids = [
        source_id
        for validated in validated_reports
        for source_id in validated["source_ids"]
    ]
    all_asset_ids = [
        asset_id
        for validated in validated_reports
        for asset_id in validated["asset_ids"]
    ]
    all_finding_ids = [
        finding_id
        for validated in validated_reports
        for finding_id in validated["finding_ids"]
    ]
    all_action_ids = [
        action_id
        for validated in validated_reports
        for action_id in validated["action_ids"]
    ]
    _reject_duplicates(all_source_ids, "source_id")
    _reject_duplicates(all_asset_ids, "asset_id")
    _reject_duplicates(all_finding_ids, "finding_id")
    _reject_duplicates(all_action_ids, "action_id")

    evidence_sources = [
        deepcopy(source)
        for report in reports
        for source in report["evidence_sources"]
    ]
    assets = [deepcopy(asset) for report in reports for asset in report["assets"]]
    findings = [
        deepcopy(finding) for report in reports for finding in report["findings"]
    ]
    recommended_actions = [
        deepcopy(action)
        for report in reports
        for action in report["recommended_actions"]
    ]

    statuses = [validated["overall_status"] for validated in validated_reports]
    statuses.extend(_finding_status(finding) for finding in findings)
    overall_status = max(statuses, key=STATUS_PRIORITY.__getitem__)

    provenance_inputs = [
        {
            "input_identifier": identifier,
            "timestamp": report["timestamp"],
            "schema_version": report["schema_version"],
            "report_type": report["report_type"],
            "evidence_source_ids": sorted(validated["source_ids"]),
            "overall_resilience_status": validated["overall_status"],
        }
        for identifier, report, validated in zip(
            identifiers,
            reports,
            validated_reports,
            strict=True,
        )
    ]

    return {
        "schema_version": UNIFIED_SCHEMA_VERSION,
        "timestamp": max(
            validated_reports,
            key=lambda validated: (
                validated["parsed_timestamp"],
                validated["report"]["timestamp"],
            ),
        )["report"]["timestamp"],
        "platform": platforms.pop(),
        "report_type": UNIFIED_REPORT_TYPE,
        "data_classification": data_classifications.pop(),
        "overall_resilience_status": overall_status,
        "provenance": {
            "composer": COMPOSER_NAME,
            "input_reports": sorted(
                provenance_inputs,
                key=lambda item: item["input_identifier"],
            ),
        },
        "evidence_sources": sorted(evidence_sources, key=lambda item: item["source_id"]),
        "assets": sorted(assets, key=lambda item: item["asset_id"]),
        "findings": sorted(findings, key=lambda item: item["finding_id"]),
        "recommended_actions": sorted(recommended_actions, key=_canonical_json),
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compose existing Unified Resilience Reports deterministically."
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="Input JSON report paths.")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON path.")
    return parser.parse_args(argv)


def _load_report(path: Path) -> dict:
    with path.open(encoding="utf-8") as report_file:
        return json.load(report_file)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if len(args.inputs) < 2:
            raise ValueError("At least two input files are required.")

        resolved_inputs = [path.resolve() for path in args.inputs]
        resolved_output = args.output.resolve()
        if resolved_output in resolved_inputs:
            raise ValueError("Output path must not be identical to an input path.")
        if args.output.exists():
            raise ValueError(f"Output path already exists: {args.output}")

        reports = [_load_report(path) for path in args.inputs]
        composed = compose_unified_reports(
            reports,
            [str(path) for path in resolved_inputs],
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as output_file:
            json.dump(composed, output_file, indent=2, sort_keys=True)
            output_file.write("\n")
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Unified report composition failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
