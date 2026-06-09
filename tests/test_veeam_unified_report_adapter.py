import json
import socket
from copy import deepcopy
from pathlib import Path

import pytest

from src.tools.veeam_unified_report_adapter import (
    UNIFIED_SCHEMA_VERSION,
    VEEAM_SCHEMA_VERSION,
    adapt_veeam_report_to_unified,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VEEAM_EXAMPLE_REPORT_PATH = (
    PROJECT_ROOT / "docs" / "example_veeam_evidence_report.json"
)

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


def load_veeam_example_report() -> dict:
    with VEEAM_EXAMPLE_REPORT_PATH.open(encoding="utf-8") as report_file:
        return json.load(report_file)


def make_all_pass_report() -> dict:
    report = load_veeam_example_report()
    for collection_name in (
        "backup_jobs",
        "repositories",
        "restore_points",
        "storage_targets",
    ):
        for resource in report[collection_name]:
            resource["evidence"] = {
                "status": "PASS",
                "reason": "MockEvidencePassed",
                "message": "The mock evidence passed.",
            }
    report["overall_status"] = "HEALTHY"
    return report


def make_incomplete_report() -> dict:
    report = make_all_pass_report()
    report["restore_points"][0]["evidence"] = {
        "status": "UNKNOWN",
        "reason": "MockEvidenceIncomplete",
        "message": "The mock evidence is incomplete.",
    }
    report["overall_status"] = "INCOMPLETE"
    return report


def test_mock_veeam_evidence_contract_v1_example():
    report = load_veeam_example_report()

    assert report["schema_version"] == VEEAM_SCHEMA_VERSION
    assert report["report_type"] == "veeam_evidence_report"
    assert report["data_classification"] == "MOCK_EXAMPLE_ONLY"
    assert report["collector"] == {
        "name": "mock_veeam_evidence_collector",
        "mode": "mock_only",
    }
    assert report["overall_status"] == "AT_RISK"
    assert {
        resource["evidence"]["status"]
        for collection_name in (
            "backup_jobs",
            "repositories",
            "restore_points",
            "storage_targets",
        )
        for resource in report[collection_name]
    } == {"PASS", "FAIL", "UNKNOWN"}


def test_valid_veeam_report_maps_successfully_and_deterministically():
    source_report = load_veeam_example_report()

    first_result = adapt_veeam_report_to_unified(source_report)
    second_result = adapt_veeam_report_to_unified(source_report)

    assert first_result == second_result
    assert first_result["schema_version"] == UNIFIED_SCHEMA_VERSION
    assert first_result["overall_resilience_status"] == "AT_RISK"
    assert first_result["source_overall_status"] == "AT_RISK"


def test_missing_schema_version_is_rejected():
    report = load_veeam_example_report()
    del report["schema_version"]

    with pytest.raises(ValueError, match="schema_version is required"):
        adapt_veeam_report_to_unified(report)


def test_unsupported_schema_version_is_rejected():
    report = load_veeam_example_report()
    report["schema_version"] = "veeam-evidence-report/v2"

    with pytest.raises(ValueError, match="Unsupported Veeam report schema_version"):
        adapt_veeam_report_to_unified(report)


def test_non_mock_collector_is_rejected():
    report = load_veeam_example_report()
    report["collector"]["mode"] = "api"

    with pytest.raises(ValueError, match="requires the mock-only collector"):
        adapt_veeam_report_to_unified(report)


def test_resource_missing_required_contract_field_is_rejected():
    report = load_veeam_example_report()
    del report["backup_jobs"][0]["repository_id"]

    with pytest.raises(ValueError, match="'repository_id' must be a non-empty string"):
        adapt_veeam_report_to_unified(report)


def test_pass_fail_and_unknown_evidence_statuses_are_preserved():
    mapped_report = adapt_veeam_report_to_unified(load_veeam_example_report())
    assets_by_type = {
        asset["resource_type"]: asset for asset in mapped_report["assets"]
    }

    assert assets_by_type["backup_job"]["source_evidence"]["status"] == "PASS"
    assert assets_by_type["restore_point"]["source_evidence"]["status"] == "UNKNOWN"
    assert assets_by_type["storage_target"]["source_evidence"]["status"] == "FAIL"

    findings_by_category = {
        finding["category"]: finding for finding in mapped_report["findings"]
    }
    assert findings_by_category["storage_target_evidence"][
        "confirmed_vulnerability"
    ] is True
    assert findings_by_category["restore_point_evidence"][
        "confirmed_vulnerability"
    ] is False


@pytest.mark.parametrize(
    ("source_report", "expected_status", "expected_source_status"),
    [
        (make_all_pass_report, "HEALTHY", "PASS"),
        (make_incomplete_report, "INCOMPLETE", "UNKNOWN"),
        (load_veeam_example_report, "AT_RISK", "FAIL"),
    ],
)
def test_overall_status_semantics(
    source_report,
    expected_status,
    expected_source_status,
):
    mapped_report = adapt_veeam_report_to_unified(source_report())

    assert mapped_report["overall_resilience_status"] == expected_status
    assert mapped_report["source_overall_status"] == expected_status
    assert mapped_report["evidence_sources"][0]["status"] == expected_source_status


def test_inconsistent_overall_status_is_rejected():
    report = make_incomplete_report()
    report["overall_status"] = "HEALTHY"

    with pytest.raises(ValueError, match="does not match its evidence statuses"):
        adapt_veeam_report_to_unified(report)


def test_resources_timestamp_evidence_source_and_provenance_are_mapped():
    source_report = load_veeam_example_report()

    mapped_report = adapt_veeam_report_to_unified(source_report)
    evidence_source = mapped_report["evidence_sources"][0]
    provenance = mapped_report["provenance"]
    asset_types = {asset["resource_type"] for asset in mapped_report["assets"]}

    assert mapped_report["timestamp"] == source_report["timestamp"]
    assert asset_types == {
        "backup_job",
        "repository",
        "restore_point",
        "storage_target",
    }
    assert evidence_source["collected_at"] == source_report["timestamp"]
    assert evidence_source["source_schema_version"] == VEEAM_SCHEMA_VERSION
    assert evidence_source["collection_mode"] == "mock_only"
    assert provenance["source_schema_version"] == VEEAM_SCHEMA_VERSION
    assert provenance["source_collector"] == "mock_veeam_evidence_collector"
    assert provenance["collection_mode"] == "mock_only"
    assert provenance["evidence_origin"] == evidence_source["reference"]


def test_adapter_uses_no_live_veeam_api_or_network(monkeypatch):
    def fail_on_network(*args, **kwargs):
        raise AssertionError("The mock Veeam adapter attempted a network connection.")

    monkeypatch.setattr(socket, "create_connection", fail_on_network)
    for variable_name in (
        "VEEAM_ENDPOINT",
        "VEEAM_USERNAME",
        "VEEAM_PASSWORD",
        "VEEAM_TOKEN",
    ):
        monkeypatch.delenv(variable_name, raising=False)

    mapped_report = adapt_veeam_report_to_unified(load_veeam_example_report())

    assert mapped_report["provenance"]["collection_mode"] == "mock_only"


def test_mapped_output_conforms_to_expected_unified_report_contract():
    mapped_report = adapt_veeam_report_to_unified(load_veeam_example_report())

    assert REQUIRED_UNIFIED_FIELDS <= mapped_report.keys()
    assert mapped_report["schema_version"] == UNIFIED_SCHEMA_VERSION
    assert mapped_report["report_type"] == "unified_resilience_report"
    assert mapped_report["assets"]
    assert all(REQUIRED_ASSET_FIELDS <= asset.keys() for asset in mapped_report["assets"])
    assert all(asset["risk_score"] is None for asset in mapped_report["assets"])
    assert all(asset["recommended_action"] is None for asset in mapped_report["assets"])
    assert mapped_report["recommended_actions"] == []


def test_source_report_is_not_modified():
    source_report = load_veeam_example_report()
    original_report = deepcopy(source_report)

    adapt_veeam_report_to_unified(source_report)

    assert source_report == original_report
