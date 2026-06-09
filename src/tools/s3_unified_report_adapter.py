S3_SCHEMA_VERSION = "s3-security-report/v1"
UNIFIED_SCHEMA_VERSION = "1.0.0"
PLATFORM_NAME = "autonomous-cyber-resilience-platform"
ADAPTER_NAME = "s3_unified_report_adapter"
SOURCE_COLLECTOR_NAME = "aws_s3_security_validator"

VALID_CHECK_STATUSES = frozenset({"PASS", "FAIL", "UNKNOWN"})
VALID_S3_OVERALL_STATUSES = frozenset({"SECURE", "INSECURE", "INCOMPLETE"})

UNIFIED_OVERALL_STATUS_BY_S3_STATUS = {
    "SECURE": "HEALTHY",
    "INSECURE": "AT_RISK",
    "INCOMPLETE": "INCOMPLETE",
}

SOURCE_STATUS_BY_S3_STATUS = {
    "SECURE": "PASS",
    "INSECURE": "FAIL",
    "INCOMPLETE": "UNKNOWN",
}


def _require_non_empty_string(report: dict, field_name: str) -> str:
    value = report.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"S3 report field '{field_name}' must be a non-empty string.")
    return value


def _validate_check(check_name: str, result) -> None:
    if not isinstance(result, dict):
        raise ValueError(f"S3 check '{check_name}' must be a structured result.")

    if set(result) != {"status", "reason", "message"}:
        raise ValueError(
            f"S3 check '{check_name}' must contain status, reason, and message."
        )

    if result["status"] not in VALID_CHECK_STATUSES:
        raise ValueError(f"S3 check '{check_name}' has an invalid status.")

    if result["reason"] is not None and not isinstance(result["reason"], str):
        raise ValueError(f"S3 check '{check_name}' has an invalid reason.")

    if not isinstance(result["message"], str) or not result["message"]:
        raise ValueError(f"S3 check '{check_name}' has an invalid message.")


def _validate_s3_report(report) -> tuple[str, str, dict, str]:
    if not isinstance(report, dict):
        raise ValueError("S3 report must be a dictionary.")

    schema_version = report.get("schema_version")
    if schema_version is None:
        raise ValueError("S3 report schema_version is required.")
    if schema_version != S3_SCHEMA_VERSION:
        raise ValueError(f"Unsupported S3 report schema_version: {schema_version}")

    timestamp = _require_non_empty_string(report, "timestamp")
    bucket = _require_non_empty_string(report, "bucket")

    checks = report.get("checks")
    if not isinstance(checks, dict) or not checks:
        raise ValueError("S3 report checks must be a non-empty dictionary.")

    for check_name, result in checks.items():
        if not isinstance(check_name, str) or not check_name:
            raise ValueError("S3 report check names must be non-empty strings.")
        _validate_check(check_name, result)

    overall_status = report.get("overall_status")
    if overall_status not in VALID_S3_OVERALL_STATUSES:
        raise ValueError("S3 report overall_status is invalid.")

    statuses = {result["status"] for result in checks.values()}
    expected_overall_status = "SECURE"
    if "FAIL" in statuses:
        expected_overall_status = "INSECURE"
    elif "UNKNOWN" in statuses:
        expected_overall_status = "INCOMPLETE"

    if overall_status != expected_overall_status:
        raise ValueError("S3 report overall_status does not match its check statuses.")

    return timestamp, bucket, checks, overall_status


def _copy_check_result(result: dict) -> dict:
    return {
        "status": result["status"],
        "reason": result["reason"],
        "message": result["message"],
    }


def adapt_s3_report_to_unified(s3_report: dict) -> dict:
    timestamp, bucket, checks, overall_status = _validate_s3_report(s3_report)

    source_id = f"aws-s3-validator:{bucket}"
    asset_id = f"aws-s3-bucket:{bucket}"
    evidence_origin = f"urn:s3-security-report:{bucket}:{timestamp}"

    mapped_checks = {
        check_name: {
            **_copy_check_result(result),
            "source_id": source_id,
            "collected_at": timestamp,
        }
        for check_name, result in checks.items()
    }

    findings = [
        {
            "finding_id": f"{asset_id}:{check_name}",
            "asset_id": asset_id,
            "category": check_name,
            **_copy_check_result(result),
            "confirmed_vulnerability": result["status"] == "FAIL",
            "source_id": source_id,
        }
        for check_name, result in checks.items()
        if result["status"] in {"FAIL", "UNKNOWN"}
    ]

    return {
        "schema_version": UNIFIED_SCHEMA_VERSION,
        "timestamp": timestamp,
        "platform": PLATFORM_NAME,
        "report_type": "unified_resilience_report",
        "data_classification": "LOCAL_ADAPTER_OUTPUT",
        "overall_resilience_status": UNIFIED_OVERALL_STATUS_BY_S3_STATUS[
            overall_status
        ],
        "source_overall_status": overall_status,
        "provenance": {
            "adapter": ADAPTER_NAME,
            "source_report_type": "s3_security_report",
            "source_schema_version": S3_SCHEMA_VERSION,
            "source_collector": SOURCE_COLLECTOR_NAME,
            "evidence_origin": evidence_origin,
        },
        "evidence_sources": [
            {
                "source_id": source_id,
                "source_type": "aws_s3_security_validator",
                "source_report_type": "s3_security_report",
                "source_schema_version": S3_SCHEMA_VERSION,
                "collector": SOURCE_COLLECTOR_NAME,
                "collected_at": timestamp,
                "status": SOURCE_STATUS_BY_S3_STATUS[overall_status],
                "source_overall_status": overall_status,
                "reference": evidence_origin,
            }
        ],
        "assets": [
            {
                "asset_id": asset_id,
                "asset_name": bucket,
                "source_type": "aws_s3",
                "backup_system": None,
                "resource_type": "s3_bucket",
                "evidence_source_id": source_id,
                "security_checks": mapped_checks,
                "risk_score": None,
                "recommended_action": None,
            }
        ],
        "findings": findings,
        "recommended_actions": [],
    }
