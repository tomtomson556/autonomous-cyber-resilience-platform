import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.tools.s3_unified_report_adapter import (
    S3_SCHEMA_VERSION,
    UNIFIED_SCHEMA_VERSION,
    adapt_s3_report_to_unified,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
S3_EXAMPLE_REPORT_PATH = PROJECT_ROOT / "docs" / "example_s3_security_report.json"

REQUIRED_UNIFIED_FIELDS = {
    "schema_version",
    "timestamp",
    "platform",
    "report_type",
    "overall_resilience_status",
    "evidence_sources",
    "assets",
    "findings",
    "recommended_actions",
}
REQUIRED_ASSET_FIELDS = {
    "asset_id",
    "source_type",
    "backup_system",
    "risk_score",
    "recommended_action",
}


def load_s3_example_report() -> dict:
    with S3_EXAMPLE_REPORT_PATH.open(encoding="utf-8") as report_file:
        return json.load(report_file)


def report_with_all_check_statuses() -> dict:
    report = load_s3_example_report()
    report["checks"]["encryption"] = {
        "status": "FAIL",
        "reason": "ApprovedEncryptionNotConfigured",
        "message": "Bucket default encryption is not approved.",
    }
    report["checks"]["object_lock"] = {
        "status": "UNKNOWN",
        "reason": "AccessDenied",
        "message": "The object lock check could not be evaluated.",
    }
    report["overall_status"] = "INSECURE"
    return report


def test_valid_s3_report_maps_successfully_and_deterministically():
    source_report = load_s3_example_report()

    first_result = adapt_s3_report_to_unified(source_report)
    second_result = adapt_s3_report_to_unified(source_report)

    assert first_result == second_result
    assert first_result["schema_version"] == UNIFIED_SCHEMA_VERSION
    assert first_result["overall_resilience_status"] == "HEALTHY"
    assert first_result["source_overall_status"] == "SECURE"


def test_missing_schema_version_is_rejected():
    source_report = load_s3_example_report()
    del source_report["schema_version"]

    with pytest.raises(ValueError, match="schema_version is required"):
        adapt_s3_report_to_unified(source_report)


def test_unsupported_schema_version_is_rejected():
    source_report = load_s3_example_report()
    source_report["schema_version"] = "s3-security-report/v2"

    with pytest.raises(ValueError, match="Unsupported S3 report schema_version"):
        adapt_s3_report_to_unified(source_report)


def test_pass_fail_and_unknown_check_statuses_are_preserved():
    source_report = report_with_all_check_statuses()

    mapped_report = adapt_s3_report_to_unified(source_report)
    mapped_checks = mapped_report["assets"][0]["security_checks"]

    assert mapped_checks["versioning"]["status"] == "PASS"
    assert mapped_checks["encryption"]["status"] == "FAIL"
    assert mapped_checks["object_lock"]["status"] == "UNKNOWN"
    assert mapped_report["source_overall_status"] == "INSECURE"
    assert mapped_report["overall_resilience_status"] == "AT_RISK"

    findings = {
        finding["category"]: finding for finding in mapped_report["findings"]
    }
    assert findings["encryption"]["confirmed_vulnerability"] is True
    assert findings["object_lock"]["confirmed_vulnerability"] is False


def test_incomplete_s3_report_maps_to_incomplete_unified_report():
    source_report = load_s3_example_report()
    source_report["checks"]["object_lock"] = {
        "status": "UNKNOWN",
        "reason": "AccessDenied",
        "message": "The object lock check could not be evaluated.",
    }
    source_report["overall_status"] = "INCOMPLETE"

    mapped_report = adapt_s3_report_to_unified(source_report)

    assert mapped_report["source_overall_status"] == "INCOMPLETE"
    assert mapped_report["overall_resilience_status"] == "INCOMPLETE"
    assert mapped_report["evidence_sources"][0]["status"] == "UNKNOWN"


def test_bucket_timestamp_evidence_source_and_provenance_are_mapped():
    source_report = load_s3_example_report()

    mapped_report = adapt_s3_report_to_unified(source_report)
    evidence_source = mapped_report["evidence_sources"][0]
    asset = mapped_report["assets"][0]
    provenance = mapped_report["provenance"]

    assert mapped_report["timestamp"] == source_report["timestamp"]
    assert asset["asset_name"] == source_report["bucket"]
    assert asset["resource_type"] == "s3_bucket"
    assert evidence_source["collected_at"] == source_report["timestamp"]
    assert evidence_source["source_type"] == "aws_s3_security_validator"
    assert evidence_source["source_schema_version"] == S3_SCHEMA_VERSION
    assert provenance["source_report_type"] == "s3_security_report"
    assert provenance["source_schema_version"] == S3_SCHEMA_VERSION
    assert provenance["source_collector"] == "aws_s3_security_validator"
    assert provenance["evidence_origin"] == evidence_source["reference"]


def test_adapter_does_not_require_aws_configuration(monkeypatch):
    for variable_name in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_DEFAULT_REGION",
        "AWS_PROFILE",
        "BUCKET_NAME",
    ):
        monkeypatch.delenv(variable_name, raising=False)

    mapped_report = adapt_s3_report_to_unified(load_s3_example_report())

    assert mapped_report["assets"][0]["source_type"] == "aws_s3"


def test_mapped_output_conforms_to_expected_unified_report_contract():
    mapped_report = adapt_s3_report_to_unified(report_with_all_check_statuses())

    assert REQUIRED_UNIFIED_FIELDS <= mapped_report.keys()
    assert mapped_report["schema_version"] == UNIFIED_SCHEMA_VERSION
    assert mapped_report["report_type"] == "unified_resilience_report"
    assert mapped_report["overall_resilience_status"] in {
        "HEALTHY",
        "AT_RISK",
        "INCOMPLETE",
        "CRITICAL",
    }
    assert mapped_report["assets"]
    assert REQUIRED_ASSET_FIELDS <= mapped_report["assets"][0].keys()
    assert mapped_report["assets"][0]["risk_score"] is None
    assert mapped_report["assets"][0]["recommended_action"] is None
    assert mapped_report["recommended_actions"] == []


def test_source_report_is_not_modified():
    source_report = load_s3_example_report()
    original_report = deepcopy(source_report)

    adapt_s3_report_to_unified(source_report)

    assert source_report == original_report


def test_inconsistent_source_overall_status_is_rejected():
    source_report = load_s3_example_report()
    source_report["overall_status"] = "INSECURE"

    with pytest.raises(ValueError, match="does not match its check statuses"):
        adapt_s3_report_to_unified(source_report)
