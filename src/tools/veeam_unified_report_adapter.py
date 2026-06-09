VEEAM_SCHEMA_VERSION = "veeam-evidence-report/v1"
UNIFIED_SCHEMA_VERSION = "1.0.0"
PLATFORM_NAME = "autonomous-cyber-resilience-platform"
ADAPTER_NAME = "veeam_unified_report_adapter"
MOCK_COLLECTOR_NAME = "mock_veeam_evidence_collector"

VALID_EVIDENCE_STATUSES = frozenset({"PASS", "FAIL", "UNKNOWN"})
VALID_OVERALL_STATUSES = frozenset({"HEALTHY", "AT_RISK", "INCOMPLETE"})

RESOURCE_DEFINITIONS = (
    (
        "backup_jobs",
        "backup_job",
        "job_id",
        "job_name",
        ("job_id", "job_name", "workload_type", "repository_id", "last_successful_backup"),
    ),
    (
        "repositories",
        "repository",
        "repository_id",
        "repository_name",
        ("repository_id", "repository_name", "storage_target_id"),
    ),
    (
        "restore_points",
        "restore_point",
        "restore_point_id",
        "restore_point_id",
        ("restore_point_id", "job_id", "created_at"),
    ),
    (
        "storage_targets",
        "storage_target",
        "storage_target_id",
        "storage_target_id",
        ("storage_target_id", "target_type"),
    ),
)

SOURCE_STATUS_BY_OVERALL_STATUS = {
    "HEALTHY": "PASS",
    "AT_RISK": "FAIL",
    "INCOMPLETE": "UNKNOWN",
}


def _require_non_empty_string(value, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Veeam report field '{field_name}' must be a non-empty string.")
    return value


def _copy_evidence(evidence: dict) -> dict:
    return {
        "status": evidence["status"],
        "reason": evidence["reason"],
        "message": evidence["message"],
    }


def _validate_evidence(resource_type: str, resource_id: str, evidence) -> None:
    if not isinstance(evidence, dict):
        raise ValueError(f"Veeam {resource_type} '{resource_id}' evidence is required.")

    if set(evidence) != {"status", "reason", "message"}:
        raise ValueError(
            f"Veeam {resource_type} '{resource_id}' evidence must contain "
            "status, reason, and message."
        )

    if evidence["status"] not in VALID_EVIDENCE_STATUSES:
        raise ValueError(f"Veeam {resource_type} '{resource_id}' status is invalid.")

    if evidence["reason"] is not None and not isinstance(evidence["reason"], str):
        raise ValueError(f"Veeam {resource_type} '{resource_id}' reason is invalid.")

    if not isinstance(evidence["message"], str) or not evidence["message"]:
        raise ValueError(f"Veeam {resource_type} '{resource_id}' message is invalid.")


def _validate_resources(report: dict) -> list[tuple[str, str, str, dict]]:
    resources = []
    seen_resource_ids = set()

    for (
        collection_name,
        resource_type,
        id_field,
        name_field,
        required_fields,
    ) in RESOURCE_DEFINITIONS:
        collection = report.get(collection_name)
        if not isinstance(collection, list):
            raise ValueError(f"Veeam report field '{collection_name}' must be a list.")

        for resource in collection:
            if not isinstance(resource, dict):
                raise ValueError(f"Veeam {resource_type} entries must be dictionaries.")

            resource_id = _require_non_empty_string(resource.get(id_field), id_field)
            resource_name = _require_non_empty_string(
                resource.get(name_field),
                name_field,
            )
            for required_field in required_fields:
                _require_non_empty_string(
                    resource.get(required_field),
                    required_field,
                )

            if resource_id in seen_resource_ids:
                raise ValueError(f"Duplicate Veeam resource identifier: {resource_id}")

            _validate_evidence(resource_type, resource_id, resource.get("evidence"))
            seen_resource_ids.add(resource_id)
            resources.append((resource_type, resource_id, resource_name, resource))

    if not resources:
        raise ValueError("Veeam report must contain at least one evidence resource.")

    return resources


def _validate_veeam_report(report) -> tuple[str, str, list[tuple[str, str, str, dict]]]:
    if not isinstance(report, dict):
        raise ValueError("Veeam report must be a dictionary.")

    schema_version = report.get("schema_version")
    if schema_version is None:
        raise ValueError("Veeam report schema_version is required.")
    if schema_version != VEEAM_SCHEMA_VERSION:
        raise ValueError(f"Unsupported Veeam report schema_version: {schema_version}")

    timestamp = _require_non_empty_string(report.get("timestamp"), "timestamp")
    if report.get("report_type") != "veeam_evidence_report":
        raise ValueError("Veeam report_type must be 'veeam_evidence_report'.")
    if report.get("data_classification") != "MOCK_EXAMPLE_ONLY":
        raise ValueError("Veeam Evidence Contract v1 accepts mock example data only.")

    collector = report.get("collector")
    if not isinstance(collector, dict) or collector != {
        "name": MOCK_COLLECTOR_NAME,
        "mode": "mock_only",
    }:
        raise ValueError("Veeam Evidence Contract v1 requires the mock-only collector.")

    resources = _validate_resources(report)
    evidence_statuses = {
        resource["evidence"]["status"] for _, _, _, resource in resources
    }

    expected_overall_status = "HEALTHY"
    if "FAIL" in evidence_statuses:
        expected_overall_status = "AT_RISK"
    elif "UNKNOWN" in evidence_statuses:
        expected_overall_status = "INCOMPLETE"

    overall_status = report.get("overall_status")
    if overall_status not in VALID_OVERALL_STATUSES:
        raise ValueError("Veeam report overall_status is invalid.")
    if overall_status != expected_overall_status:
        raise ValueError(
            "Veeam report overall_status does not match its evidence statuses."
        )

    return timestamp, overall_status, resources


def _resource_details(resource: dict) -> dict:
    return {
        field_name: field_value
        for field_name, field_value in resource.items()
        if field_name != "evidence"
    }


def adapt_veeam_report_to_unified(veeam_report: dict) -> dict:
    timestamp, overall_status, resources = _validate_veeam_report(veeam_report)

    source_id = f"mock-veeam-evidence:{timestamp}"
    evidence_origin = f"urn:veeam-evidence-report:mock:{timestamp}"

    assets = []
    findings = []
    for resource_type, resource_id, resource_name, resource in resources:
        asset_id = f"veeam-{resource_type}:{resource_id}"
        evidence = resource["evidence"]

        assets.append(
            {
                "asset_id": asset_id,
                "asset_name": resource_name,
                "source_type": "veeam",
                "backup_system": "veeam",
                "resource_type": resource_type,
                "evidence_source_id": source_id,
                "source_evidence": {
                    **_copy_evidence(evidence),
                    "collected_at": timestamp,
                    "details": _resource_details(resource),
                },
                "risk_score": None,
                "recommended_action": None,
            }
        )

        if evidence["status"] in {"FAIL", "UNKNOWN"}:
            findings.append(
                {
                    "finding_id": f"{asset_id}:evidence",
                    "asset_id": asset_id,
                    "category": f"{resource_type}_evidence",
                    **_copy_evidence(evidence),
                    "confirmed_vulnerability": evidence["status"] == "FAIL",
                    "source_id": source_id,
                }
            )

    return {
        "schema_version": UNIFIED_SCHEMA_VERSION,
        "timestamp": timestamp,
        "platform": PLATFORM_NAME,
        "report_type": "unified_resilience_report",
        "data_classification": "MOCK_EXAMPLE_ONLY",
        "overall_resilience_status": overall_status,
        "source_overall_status": overall_status,
        "provenance": {
            "adapter": ADAPTER_NAME,
            "source_report_type": "veeam_evidence_report",
            "source_schema_version": VEEAM_SCHEMA_VERSION,
            "source_collector": MOCK_COLLECTOR_NAME,
            "evidence_origin": evidence_origin,
            "collection_mode": "mock_only",
        },
        "evidence_sources": [
            {
                "source_id": source_id,
                "source_type": "veeam_mock_evidence",
                "source_report_type": "veeam_evidence_report",
                "source_schema_version": VEEAM_SCHEMA_VERSION,
                "collector": MOCK_COLLECTOR_NAME,
                "collection_mode": "mock_only",
                "collected_at": timestamp,
                "status": SOURCE_STATUS_BY_OVERALL_STATUS[overall_status],
                "source_overall_status": overall_status,
                "reference": evidence_origin,
            }
        ],
        "assets": assets,
        "findings": findings,
        "recommended_actions": [],
    }
