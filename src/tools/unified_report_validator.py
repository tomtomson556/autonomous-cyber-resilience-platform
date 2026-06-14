from datetime import datetime


UNIFIED_SCHEMA_VERSION = "1.0.0"
UNIFIED_REPORT_TYPE = "unified_resilience_report"

VALID_EVIDENCE_STATUSES = frozenset({"PASS", "FAIL", "UNKNOWN"})
VALID_OVERALL_STATUSES = frozenset(
    {"HEALTHY", "INCOMPLETE", "AT_RISK", "CRITICAL"}
)

REQUIRED_EVIDENCE_SOURCE_FIELDS = frozenset(
    {"source_id", "source_type", "collected_at", "status", "reference"}
)
REQUIRED_ASSET_FIELDS = frozenset(
    {"asset_id", "source_type", "backup_system", "risk_score", "recommended_action"}
)
REQUIRED_FINDING_FIELDS = frozenset(
    {
        "finding_id",
        "asset_id",
        "category",
        "status",
        "reason",
        "message",
        "confirmed_vulnerability",
    }
)
SOURCE_REFERENCE_FIELDS = frozenset({"source_id", "evidence_source_id"})
SOURCE_REFERENCE_LIST_FIELDS = frozenset({"evidence_source_ids"})
ACTION_REFERENCE_FIELDS = {
    "asset_id": "asset",
    "finding_id": "finding",
    "source_id": "source",
    "evidence_source_id": "source",
}
ACTION_REFERENCE_LIST_FIELDS = {
    "evidence_source_ids": "source",
    "source_ids": "source",
    "source_evidence_ids": "source",
    "asset_ids": "asset",
    "finding_ids": "finding",
}
KNOWN_ASSET_EVIDENCE_FIELDS = frozenset(
    {
        "backup_job",
        "immutability_evidence",
        "restore_test_evidence",
        "rpo_evaluation",
        "rto_evaluation",
        "source_evidence",
        "successful_backup_session",
    }
)
TIMESTAMP_FIELD_NAMES = frozenset({"timestamp", "last_successful_backup", "created_at"})


def _require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Unified report field '{field_name}' must be a non-empty string.")
    return value


def _require_fields(value: dict, required: frozenset[str], field_name: str) -> None:
    missing = sorted(required - value.keys())
    if missing:
        raise ValueError(f"Unified report field '{field_name}' is missing fields: {missing}")


def _require_list(report: dict, field_name: str, *, non_empty: bool = False) -> list:
    value = report.get(field_name)
    if not isinstance(value, list) or (non_empty and not value):
        requirement = "a non-empty list" if non_empty else "a list"
        raise ValueError(f"Unified report field '{field_name}' must be {requirement}.")
    return value


def _parse_utc_timestamp(value: object, field_name: str) -> datetime:
    timestamp = _require_non_empty_string(value, field_name)
    if "T" not in timestamp or not (
        timestamp.endswith("Z") or timestamp.endswith("+00:00")
    ):
        raise ValueError(f"Unified report field '{field_name}' must be a UTC timestamp.")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            f"Unified report field '{field_name}' must be valid ISO 8601."
        ) from error
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"Unified report field '{field_name}' must be a UTC timestamp.")
    return parsed


def _validate_allowed_status(
    value: object,
    field_name: str,
    allowed_statuses: frozenset[str],
    *,
    invalid_message: str | None = None,
) -> None:
    if not isinstance(value, str):
        raise ValueError(f"Unified report field '{field_name}' status must be a string.")
    if value not in allowed_statuses:
        raise ValueError(
            invalid_message
            or f"Unified report field '{field_name}' has an invalid status."
        )


def _validate_embedded_contract(value: object, field_name: str) -> None:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            nested_field = f"{field_name}.{key}" if field_name else key
            if (
                key in TIMESTAMP_FIELD_NAMES or key.endswith("_at")
            ) and nested_value is not None:
                _parse_utc_timestamp(nested_value, nested_field)
            _validate_embedded_contract(nested_value, nested_field)
    elif isinstance(value, list):
        for index, nested_value in enumerate(value):
            _validate_embedded_contract(nested_value, f"{field_name}[{index}]")


def _validate_known_asset_evidence_statuses(asset: dict, field_name: str) -> None:
    for evidence_field in KNOWN_ASSET_EVIDENCE_FIELDS & asset.keys():
        evidence = asset[evidence_field]
        if isinstance(evidence, dict) and "status" in evidence:
            _validate_allowed_status(
                evidence["status"],
                f"{field_name}.{evidence_field}.status",
                VALID_EVIDENCE_STATUSES,
            )

    security_checks = asset.get("security_checks")
    if isinstance(security_checks, dict):
        for check_name, check in security_checks.items():
            if isinstance(check, dict) and "status" in check:
                _validate_allowed_status(
                    check["status"],
                    f"{field_name}.security_checks.{check_name}.status",
                    VALID_EVIDENCE_STATUSES,
                )


def _validate_unique_ids(
    entries: list,
    collection_name: str,
    id_field: str,
    *,
    optional: bool = False,
) -> list[str]:
    identifiers = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(
                f"Unified report field '{collection_name}' must contain objects."
            )
        if optional and id_field not in entry:
            continue
        identifier = _require_non_empty_string(
            entry.get(id_field),
            f"{collection_name}[{index}].{id_field}",
        )
        if identifier in identifiers:
            raise ValueError(f"Duplicate Unified {id_field}: {identifier}")
        identifiers.append(identifier)
    return identifiers


def _validate_reference(
    value: object,
    field_name: str,
    valid_identifiers: set[str],
) -> None:
    identifier = _require_non_empty_string(value, field_name)
    if identifier not in valid_identifiers:
        raise ValueError(
            f"Unified report field '{field_name}' references unknown identifier: "
            f"{identifier}"
        )


def _validate_nested_source_references(
    value: object,
    field_name: str,
    source_ids: set[str],
) -> None:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            nested_field = f"{field_name}.{key}"
            if key in SOURCE_REFERENCE_FIELDS:
                _validate_reference(nested_value, nested_field, source_ids)
            if key in SOURCE_REFERENCE_LIST_FIELDS:
                if not isinstance(nested_value, list):
                    raise ValueError(
                        f"Unified report field '{nested_field}' must be a list."
                    )
                for index, identifier in enumerate(nested_value):
                    _validate_reference(
                        identifier,
                        f"{nested_field}[{index}]",
                        source_ids,
                    )
            _validate_nested_source_references(nested_value, nested_field, source_ids)
    elif isinstance(value, list):
        for index, nested_value in enumerate(value):
            _validate_nested_source_references(
                nested_value,
                f"{field_name}[{index}]",
                source_ids,
            )


def _validate_nested_action_references(
    value: object,
    field_name: str,
    reference_ids: dict[str, set[str]],
) -> None:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            nested_field = f"{field_name}.{key}"
            reference_type = ACTION_REFERENCE_FIELDS.get(key)
            if reference_type is not None:
                _validate_reference(
                    nested_value,
                    nested_field,
                    reference_ids[reference_type],
                )
            list_reference_type = ACTION_REFERENCE_LIST_FIELDS.get(key)
            if list_reference_type is not None:
                if not isinstance(nested_value, list) or not nested_value:
                    raise ValueError(
                        f"Unified report field '{nested_field}' must be a non-empty list."
                    )
                for index, identifier in enumerate(nested_value):
                    _validate_reference(
                        identifier,
                        f"{nested_field}[{index}]",
                        reference_ids[list_reference_type],
                    )
            _validate_nested_action_references(
                nested_value,
                nested_field,
                reference_ids,
            )
    elif isinstance(value, list):
        for index, nested_value in enumerate(value):
            _validate_nested_action_references(
                nested_value,
                f"{field_name}[{index}]",
                reference_ids,
            )


def validate_unified_report(report: object) -> dict:
    """Validate one Unified Resilience Report without modifying it."""
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
        raise ValueError(f"Unified report_type must be '{UNIFIED_REPORT_TYPE}'.")

    parsed_timestamp = _parse_utc_timestamp(report.get("timestamp"), "timestamp")
    platform = _require_non_empty_string(report.get("platform"), "platform")
    data_classification = _require_non_empty_string(
        report.get("data_classification"),
        "data_classification",
    )
    overall_status = report.get("overall_resilience_status")
    _validate_allowed_status(
        overall_status,
        "overall_resilience_status",
        VALID_OVERALL_STATUSES,
        invalid_message="Unified report overall_resilience_status is invalid.",
    )

    evidence_sources = _require_list(report, "evidence_sources", non_empty=True)
    assets = _require_list(report, "assets", non_empty=True)
    findings = _require_list(report, "findings")
    recommended_actions = _require_list(report, "recommended_actions")

    for index, source in enumerate(evidence_sources):
        if not isinstance(source, dict):
            raise ValueError("Unified report field 'evidence_sources' must contain objects.")
        _require_fields(
            source,
            REQUIRED_EVIDENCE_SOURCE_FIELDS,
            f"evidence_sources[{index}]",
        )
        _require_non_empty_string(
            source["source_type"],
            f"evidence_sources[{index}].source_type",
        )
        _require_non_empty_string(
            source["reference"],
            f"evidence_sources[{index}].reference",
        )
        _validate_allowed_status(
            source["status"],
            f"evidence_sources[{index}].status",
            VALID_EVIDENCE_STATUSES,
        )
        _parse_utc_timestamp(
            source["collected_at"],
            f"evidence_sources[{index}].collected_at",
        )

    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            raise ValueError("Unified report field 'assets' must contain objects.")
        _require_fields(asset, REQUIRED_ASSET_FIELDS, f"assets[{index}]")
        _require_non_empty_string(asset["source_type"], f"assets[{index}].source_type")
        if asset["backup_system"] is not None:
            _require_non_empty_string(
                asset["backup_system"],
                f"assets[{index}].backup_system",
            )
        for field_name in ("risk_score", "recommended_action"):
            if asset[field_name] is not None and not isinstance(asset[field_name], dict):
                raise ValueError(
                    f"Unified report field 'assets[{index}].{field_name}' "
                    "must be an object or null."
                )
        _validate_known_asset_evidence_statuses(asset, f"assets[{index}]")

    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise ValueError("Unified report field 'findings' must contain objects.")
        _require_fields(finding, REQUIRED_FINDING_FIELDS, f"findings[{index}]")
        _require_non_empty_string(finding["category"], f"findings[{index}].category")
        _require_non_empty_string(finding["message"], f"findings[{index}].message")
        _validate_allowed_status(
            finding["status"],
            f"findings[{index}].status",
            VALID_EVIDENCE_STATUSES,
        )
        if finding["reason"] is not None:
            _require_non_empty_string(finding["reason"], f"findings[{index}].reason")
        if not isinstance(finding["confirmed_vulnerability"], bool):
            raise ValueError(
                f"Unified finding '{finding['finding_id']}' "
                "confirmed_vulnerability must be a boolean."
            )
        if finding["status"] == "UNKNOWN" and finding["confirmed_vulnerability"]:
            raise ValueError(
                f"Unified finding '{finding['finding_id']}' cannot confirm UNKNOWN evidence."
            )

    source_ids = set(
        _validate_unique_ids(evidence_sources, "evidence_sources", "source_id")
    )
    asset_ids = set(_validate_unique_ids(assets, "assets", "asset_id"))
    finding_ids = set(_validate_unique_ids(findings, "findings", "finding_id"))
    action_ids = _validate_unique_ids(
        recommended_actions,
        "recommended_actions",
        "action_id",
        optional=True,
    )

    for index, asset in enumerate(assets):
        _validate_nested_source_references(asset, f"assets[{index}]", source_ids)
    for index, finding in enumerate(findings):
        _validate_reference(
            finding["asset_id"],
            f"findings[{index}].asset_id",
            asset_ids,
        )
        _validate_nested_source_references(finding, f"findings[{index}]", source_ids)
    action_reference_ids = {
        "asset": asset_ids,
        "finding": finding_ids,
        "source": source_ids,
    }
    for index, action in enumerate(recommended_actions):
        _validate_nested_action_references(
            action,
            f"recommended_actions[{index}]",
            action_reference_ids,
        )

    _validate_embedded_contract(report, "")

    return {
        "report": report,
        "parsed_timestamp": parsed_timestamp,
        "platform": platform,
        "data_classification": data_classification,
        "overall_status": overall_status,
        "source_ids": sorted(source_ids),
        "asset_ids": sorted(asset_ids),
        "finding_ids": sorted(finding_ids),
        "action_ids": sorted(action_ids),
        "assets_by_id": {asset["asset_id"]: asset for asset in assets},
        "evidence_source_ids": source_ids,
    }
