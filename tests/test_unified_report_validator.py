import re
from copy import deepcopy

import pytest

from src.tools.s3_unified_report_adapter import adapt_s3_report_to_unified
from src.tools.unified_report_validator import validate_unified_report
from src.tools.veeam_unified_report_adapter import adapt_veeam_report_to_unified
from tests.test_s3_unified_report_adapter import load_s3_example_report
from tests.test_unified_report_composer import unified_report
from tests.test_veeam_unified_report_adapter import load_veeam_example_report


def valid_report() -> dict:
    report = unified_report("validator", finding_status="UNKNOWN")
    report["assets"][0]["evidence_source_id"] = "source-validator"
    report["findings"][0]["source_id"] = "source-validator"
    report["recommended_actions"] = [
        {
            "action_id": "action-validator",
            "asset_id": "asset-validator",
            "finding_id": "finding-validator",
            "source_id": "source-validator",
            "summary": "Review the finding.",
        }
    ]
    return report


def test_valid_s3_and_veeam_adapter_reports_are_accepted():
    s3_report = adapt_s3_report_to_unified(load_s3_example_report())
    veeam_report = adapt_veeam_report_to_unified(load_veeam_example_report())

    assert validate_unified_report(s3_report)["asset_ids"]
    assert validate_unified_report(veeam_report)["asset_ids"]


def test_optional_reference_fields_remain_optional():
    report = unified_report("optional")

    validate_unified_report(report)


@pytest.mark.parametrize(
    ("location", "field_name", "unknown_value"),
    [
        ("asset", "evidence_source_id", "unknown-source"),
        ("finding", "asset_id", "unknown-asset"),
        ("finding", "source_id", "unknown-source"),
        ("action", "asset_id", "unknown-asset"),
        ("action", "finding_id", "unknown-finding"),
        ("action", "source_id", "unknown-source"),
    ],
)
def test_unknown_references_are_rejected(location, field_name, unknown_value):
    report = valid_report()
    target = {
        "asset": report["assets"][0],
        "finding": report["findings"][0],
        "action": report["recommended_actions"][0],
    }[location]
    target[field_name] = unknown_value

    with pytest.raises(ValueError, match="references unknown identifier"):
        validate_unified_report(report)


@pytest.mark.parametrize(
    ("collection_name", "id_field"),
    [
        ("evidence_sources", "source_id"),
        ("assets", "asset_id"),
        ("findings", "finding_id"),
        ("recommended_actions", "action_id"),
    ],
)
def test_duplicate_collection_ids_are_rejected(collection_name, id_field):
    report = valid_report()
    duplicate = deepcopy(report[collection_name][0])
    report[collection_name].append(duplicate)

    with pytest.raises(ValueError, match=f"Duplicate Unified {id_field}"):
        validate_unified_report(report)


@pytest.mark.parametrize(
    ("location", "field_name"),
    [
        ("source", "source_id"),
        ("asset", "asset_id"),
        ("finding", "finding_id"),
        ("action", "action_id"),
    ],
)
def test_whitespace_only_ids_are_rejected(location, field_name):
    report = valid_report()
    target = {
        "source": report["evidence_sources"][0],
        "asset": report["assets"][0],
        "finding": report["findings"][0],
        "action": report["recommended_actions"][0],
    }[location]
    target[field_name] = "   "

    with pytest.raises(ValueError, match="must be a non-empty string"):
        validate_unified_report(report)


def test_invalid_finding_status_is_rejected():
    report = valid_report()
    report["findings"][0]["status"] = "INVALID"

    with pytest.raises(ValueError, match="invalid status"):
        validate_unified_report(report)


def test_invalid_overall_status_is_rejected():
    report = valid_report()
    report["overall_resilience_status"] = "UNKNOWN"

    with pytest.raises(ValueError, match="overall_resilience_status is invalid"):
        validate_unified_report(report)


@pytest.mark.parametrize(
    ("location", "field_path"),
    [
        ("overall", "overall_resilience_status"),
        ("source", "evidence_sources[0].status"),
        ("finding", "findings[0].status"),
    ],
)
def test_non_string_statuses_are_rejected_with_value_error(location, field_path):
    report = valid_report()
    if location == "overall":
        report["overall_resilience_status"] = []
    elif location == "source":
        report["evidence_sources"][0]["status"] = []
    else:
        report["findings"][0]["status"] = []

    with pytest.raises(ValueError, match=re.escape(field_path)):
        validate_unified_report(report)


@pytest.mark.parametrize(
    ("field_name", "unknown_identifier"),
    [
        ("evidence_source_ids", "unknown-source"),
        ("source_ids", "unknown-source"),
        ("source_evidence_ids", "unknown-source"),
        ("asset_ids", "unknown-asset"),
        ("finding_ids", "unknown-finding"),
    ],
)
def test_action_unknown_list_references_are_rejected(field_name, unknown_identifier):
    report = valid_report()
    report["recommended_actions"][0]["parameters"] = {
        field_name: [unknown_identifier]
    }

    with pytest.raises(ValueError, match="references unknown identifier"):
        validate_unified_report(report)


@pytest.mark.parametrize(
    "field_name",
    ["evidence_source_ids", "asset_ids", "finding_ids"],
)
def test_action_empty_reference_lists_are_rejected(field_name):
    report = valid_report()
    report["recommended_actions"][0]["parameters"] = {field_name: []}

    with pytest.raises(ValueError, match=rf"parameters\.{field_name}.*non-empty list"):
        validate_unified_report(report)


@pytest.mark.parametrize(
    ("field_name", "invalid_identifier"),
    [
        ("asset_ids", "   "),
        ("finding_ids", {}),
    ],
)
def test_action_invalid_reference_list_items_are_rejected(
    field_name,
    invalid_identifier,
):
    report = valid_report()
    report["recommended_actions"][0]["parameters"] = {
        field_name: [invalid_identifier]
    }

    with pytest.raises(ValueError, match=rf"parameters\.{field_name}\[0\]"):
        validate_unified_report(report)


def test_action_valid_nested_reference_lists_are_accepted():
    report = valid_report()
    report["recommended_actions"][0]["parameters"] = {
        "evidence_source_ids": ["source-validator"],
        "source_ids": ["source-validator"],
        "source_evidence_ids": ["source-validator"],
        "asset_ids": ["asset-validator"],
        "finding_ids": ["finding-validator"],
    }

    validate_unified_report(report)


def test_action_nested_unknown_asset_reference_is_rejected():
    report = valid_report()
    report["recommended_actions"][0]["parameters"] = {"asset_id": "unknown-asset"}

    with pytest.raises(ValueError, match="references unknown identifier"):
        validate_unified_report(report)


def test_action_open_status_metadata_is_accepted():
    report = valid_report()
    report["recommended_actions"][0]["status"] = "PENDING"
    report["recommended_actions"][0]["parameters"] = {
        "asset_id": "asset-validator",
        "finding_id": "finding-validator",
        "evidence_source_ids": ["source-validator"],
    }

    validate_unified_report(report)


@pytest.mark.parametrize(
    ("location", "field_name", "value"),
    [
        ("source", "source_type", 42),
        ("asset", "backup_system", 42),
        ("asset", "risk_score", "invalid"),
        ("asset", "recommended_action", "invalid"),
        ("finding", "confirmed_vulnerability", "false"),
    ],
)
def test_invalid_required_field_types_are_rejected(location, field_name, value):
    report = valid_report()
    target = {
        "source": report["evidence_sources"][0],
        "asset": report["assets"][0],
        "finding": report["findings"][0],
    }[location]
    target[field_name] = value

    with pytest.raises(ValueError):
        validate_unified_report(report)


@pytest.mark.parametrize(
    ("location", "timestamp"),
    [
        ("report", "invalid"),
        ("report", "2026-06-12T10:00:00+05:00"),
        ("source", "invalid"),
        ("source", "2026-06-12T10:00:00+05:00"),
        ("embedded", "invalid"),
        ("embedded", "2026-06-12T10:00:00+05:00"),
    ],
)
def test_invalid_or_non_utc_timestamps_are_rejected(location, timestamp):
    report = valid_report()
    if location == "report":
        report["timestamp"] = timestamp
    elif location == "source":
        report["evidence_sources"][0]["collected_at"] = timestamp
    else:
        report["assets"][0]["source_evidence"] = {
            "status": "PASS",
            "collected_at": timestamp,
        }

    with pytest.raises(ValueError, match="UTC timestamp"):
        validate_unified_report(report)
