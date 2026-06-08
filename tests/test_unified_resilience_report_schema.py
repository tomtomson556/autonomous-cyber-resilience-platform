import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_REPORT_PATH = (
    PROJECT_ROOT / "docs" / "example_unified_resilience_report.json"
)

CHECK_STATUSES = {"PASS", "FAIL", "UNKNOWN"}
OVERALL_RESILIENCE_STATUSES = {"HEALTHY", "AT_RISK", "INCOMPLETE", "CRITICAL"}
REQUIRED_TOP_LEVEL_FIELDS = {
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


def load_example_report():
    with EXAMPLE_REPORT_PATH.open(encoding="utf-8") as report_file:
        return json.load(report_file)


def collect_check_statuses(value):
    if isinstance(value, dict):
        statuses = [value["status"]] if "status" in value else []
        for nested_value in value.values():
            statuses.extend(collect_check_statuses(nested_value))
        return statuses

    if isinstance(value, list):
        statuses = []
        for item in value:
            statuses.extend(collect_check_statuses(item))
        return statuses

    return []


def test_example_unified_resilience_report_contract():
    report = load_example_report()

    assert REQUIRED_TOP_LEVEL_FIELDS <= report.keys()
    assert report["schema_version"]
    assert report["data_classification"] == "MOCK_EXAMPLE_ONLY"
    assert report["overall_resilience_status"] in OVERALL_RESILIENCE_STATUSES
    assert isinstance(report["assets"], list)
    assert report["assets"]

    for asset in report["assets"]:
        assert REQUIRED_ASSET_FIELDS <= asset.keys()

    check_statuses = collect_check_statuses(report)
    assert set(check_statuses) <= CHECK_STATUSES
    assert "UNKNOWN" in check_statuses


def test_unknown_finding_is_not_a_confirmed_vulnerability():
    report = load_example_report()
    unknown_findings = [
        finding for finding in report["findings"] if finding["status"] == "UNKNOWN"
    ]

    assert unknown_findings
    assert all(
        finding["confirmed_vulnerability"] is False for finding in unknown_findings
    )
