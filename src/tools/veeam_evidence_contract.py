MOCK_COLLECTOR_NAME = "mock_veeam_evidence_collector"
API_READ_ONLY_COLLECTOR_NAME = "veeam_enterprise_manager_read_only_collector"

MOCK_DATA_CLASSIFICATION = "MOCK_EXAMPLE_ONLY"
API_READ_ONLY_DATA_CLASSIFICATION = "SANITIZED_OPERATIONAL_EVIDENCE"

VALID_COLLECTOR_MODES = frozenset({"mock_only", "api_read_only"})


def _validate_api_read_only_completeness_findings(report: dict) -> None:
    findings = report.get("completeness_findings")
    if not isinstance(findings, list):
        raise ValueError("Veeam api_read_only completeness_findings must be a list.")

    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != {
            "resource_type",
            "resource_id",
            "reason",
            "evidence",
        }:
            raise ValueError("Invalid Veeam api_read_only completeness finding.")

        if not isinstance(finding["resource_type"], str) or not finding["resource_type"]:
            raise ValueError("Invalid Veeam api_read_only completeness resource type.")
        if finding["resource_id"] is not None and (
            not isinstance(finding["resource_id"], str) or not finding["resource_id"]
        ):
            raise ValueError("Invalid Veeam api_read_only completeness resource ID.")
        if not isinstance(finding["reason"], str) or not finding["reason"]:
            raise ValueError("Invalid Veeam api_read_only completeness reason.")

        evidence = finding["evidence"]
        if not isinstance(evidence, dict) or set(evidence) != {
            "status",
            "reason",
            "message",
        }:
            raise ValueError("Invalid Veeam api_read_only completeness evidence.")
        if (
            evidence["status"] != "UNKNOWN"
            or evidence["reason"] != finding["reason"]
            or not isinstance(evidence["message"], str)
            or not evidence["message"]
        ):
            raise ValueError("Invalid Veeam api_read_only completeness evidence.")


def validate_veeam_collector_profile(report: dict) -> str:
    """Validate collector identity and classification without accessing Veeam."""
    if not isinstance(report, dict):
        raise ValueError("Veeam report must be a dictionary.")

    collector = report.get("collector")
    if not isinstance(collector, dict):
        raise ValueError("Veeam report collector profile is required.")

    mode = collector.get("mode")
    if mode not in VALID_COLLECTOR_MODES:
        raise ValueError(f"Unsupported Veeam collector mode: {mode}")

    expected_profile = {
        "mock_only": {
            "collector": {
                "name": MOCK_COLLECTOR_NAME,
                "mode": "mock_only",
            },
            "data_classification": MOCK_DATA_CLASSIFICATION,
        },
        "api_read_only": {
            "collector": {
                "name": API_READ_ONLY_COLLECTOR_NAME,
                "mode": "api_read_only",
            },
            "data_classification": API_READ_ONLY_DATA_CLASSIFICATION,
        },
    }[mode]

    if collector != expected_profile["collector"]:
        raise ValueError(f"Invalid Veeam {mode} collector profile.")

    if report.get("data_classification") != expected_profile["data_classification"]:
        raise ValueError(f"Invalid Veeam {mode} data classification.")

    if mode == "api_read_only":
        _validate_api_read_only_completeness_findings(report)

    return mode
