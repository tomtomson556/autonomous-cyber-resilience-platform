import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path


SCHEMA_VERSION = "restore-test-evidence/v1"
REPORT_TYPE = "restore_test_evidence_report"

VALID_RESULTS = frozenset({"PASS", "FAIL", "UNKNOWN"})
VALID_DATA_CLASSIFICATIONS = frozenset(
    {"MOCK_EXAMPLE_ONLY", "SANITIZED_OPERATIONAL_EVIDENCE"}
)
VALID_SOURCE_TYPES = frozenset(
    {"sanitized_fixture", "manual_attestation", "external_test_record"}
)
VALID_COLLECTION_METHODS = frozenset(
    {"sanitized_fixture", "manual_import", "external_record_import"}
)
SOURCE_PROFILE = {
    "sanitized_fixture": {
        "data_classification": "MOCK_EXAMPLE_ONLY",
        "collection_method": "sanitized_fixture",
    },
    "manual_attestation": {
        "data_classification": "SANITIZED_OPERATIONAL_EVIDENCE",
        "collection_method": "manual_import",
    },
    "external_test_record": {
        "data_classification": "SANITIZED_OPERATIONAL_EVIDENCE",
        "collection_method": "external_record_import",
    },
}
VALID_RESTORE_SCOPES = frozenset(
    {"full_asset", "partial_asset", "item_level"}
)
VALID_RESTORE_TARGET_TYPES = frozenset(
    {"isolated_test_environment", "sandbox", "alternate_non_production_location"}
)

REPORT_FIELDS = frozenset(
    {
        "schema_version",
        "report_type",
        "generated_at",
        "source",
        "data_classification",
        "restore_tests",
    }
)
SOURCE_FIELDS = frozenset({"source_id", "source_type"})
RESTORE_TEST_FIELDS = frozenset(
    {
        "restore_test_id",
        "asset_id",
        "source_system",
        "source_backup_reference",
        "restore_scope",
        "restore_target_type",
        "started_at",
        "completed_at",
        "duration_seconds",
        "result",
        "reason",
        "message",
        "provenance",
    }
)
PROVENANCE_FIELDS = frozenset(
    {"source_record_id", "collected_at", "collection_method"}
)


def _require_exact_fields(value: object, expected: frozenset[str], field_name: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(
            f"Field '{field_name}' must be an object containing exactly "
            f"{sorted(expected)}."
        )
    return value


def _require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Field '{field_name}' must be a non-empty string.")
    return value


def _require_safe_reference(value: object, field_name: str) -> str:
    reference = _require_non_empty_string(value, field_name)
    lowered = reference.lower()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:_-]*", reference) or any(
        marker in lowered
        for marker in ("password", "secret", "token", "credential", "connection")
    ):
        raise ValueError(f"Field '{field_name}' must be a sanitized local reference.")
    return reference


def _parse_utc_timestamp(value: object, field_name: str) -> datetime:
    timestamp = _require_non_empty_string(value, field_name)
    if "T" not in timestamp or not (
        timestamp.endswith("Z") or timestamp.endswith("+00:00")
    ):
        raise ValueError(f"Field '{field_name}' must be a UTC timestamp.")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"Field '{field_name}' must be valid ISO 8601.") from error
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"Field '{field_name}' must be a UTC timestamp.")
    return parsed


def _validate_source(source: object) -> None:
    source = _require_exact_fields(source, SOURCE_FIELDS, "source")
    _require_safe_reference(source["source_id"], "source.source_id")
    if source["source_type"] not in VALID_SOURCE_TYPES:
        raise ValueError("Field 'source.source_type' is invalid.")


def _validate_provenance(
    provenance: object,
    field_name: str,
    expected_collection_method: str,
) -> None:
    provenance = _require_exact_fields(provenance, PROVENANCE_FIELDS, field_name)
    _require_safe_reference(
        provenance["source_record_id"],
        f"{field_name}.source_record_id",
    )
    _parse_utc_timestamp(provenance["collected_at"], f"{field_name}.collected_at")
    if provenance["collection_method"] not in VALID_COLLECTION_METHODS:
        raise ValueError(f"Field '{field_name}.collection_method' is invalid.")
    if provenance["collection_method"] != expected_collection_method:
        raise ValueError(
            f"Field '{field_name}.collection_method' does not match source profile."
        )


def _validate_timing(restore_test: dict, field_name: str) -> None:
    started_at = restore_test["started_at"]
    completed_at = restore_test["completed_at"]
    duration_seconds = restore_test["duration_seconds"]
    timing_values = (started_at, completed_at, duration_seconds)

    if all(value is None for value in timing_values):
        if restore_test["result"] != "UNKNOWN":
            raise ValueError(f"Field '{field_name}' PASS/FAIL timing is required.")
        return

    if any(value is None for value in timing_values):
        raise ValueError(f"Field '{field_name}' timing must be complete or entirely null.")
    if (
        isinstance(duration_seconds, bool)
        or not isinstance(duration_seconds, int)
        or duration_seconds < 0
    ):
        raise ValueError(f"Field '{field_name}.duration_seconds' must be non-negative.")

    started = _parse_utc_timestamp(started_at, f"{field_name}.started_at")
    completed = _parse_utc_timestamp(completed_at, f"{field_name}.completed_at")
    if completed < started:
        raise ValueError(f"Field '{field_name}.completed_at' precedes started_at.")
    observed_duration = (completed - started).total_seconds()
    if observed_duration != duration_seconds:
        raise ValueError(f"Field '{field_name}.duration_seconds' does not match timestamps.")


def _validate_restore_test(
    restore_test: object,
    index: int,
    expected_collection_method: str,
) -> str:
    field_name = f"restore_tests[{index}]"
    restore_test = _require_exact_fields(
        restore_test,
        RESTORE_TEST_FIELDS,
        field_name,
    )

    restore_test_id = _require_safe_reference(
        restore_test["restore_test_id"],
        f"{field_name}.restore_test_id",
    )
    _require_safe_reference(restore_test["asset_id"], f"{field_name}.asset_id")
    _require_safe_reference(
        restore_test["source_system"],
        f"{field_name}.source_system",
    )
    _require_safe_reference(
        restore_test["source_backup_reference"],
        f"{field_name}.source_backup_reference",
    )

    if restore_test["restore_scope"] not in VALID_RESTORE_SCOPES:
        raise ValueError(f"Field '{field_name}.restore_scope' is invalid.")
    if restore_test["restore_target_type"] not in VALID_RESTORE_TARGET_TYPES:
        raise ValueError(f"Field '{field_name}.restore_target_type' is invalid.")
    if restore_test["result"] not in VALID_RESULTS:
        raise ValueError(f"Field '{field_name}.result' is invalid.")

    _require_non_empty_string(restore_test["reason"], f"{field_name}.reason")
    _require_non_empty_string(restore_test["message"], f"{field_name}.message")
    _validate_provenance(
        restore_test["provenance"],
        f"{field_name}.provenance",
        expected_collection_method,
    )
    _validate_timing(restore_test, field_name)
    return restore_test_id


def validate_restore_test_evidence(report: object) -> dict:
    """Validate and return a deterministic deep-copied restore-test report."""
    report = _require_exact_fields(report, REPORT_FIELDS, "report")
    if report["schema_version"] != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported restore-test evidence schema_version: {report['schema_version']}"
        )
    if report["report_type"] != REPORT_TYPE:
        raise ValueError(f"Restore-test report_type must be '{REPORT_TYPE}'.")
    _parse_utc_timestamp(report["generated_at"], "generated_at")
    _validate_source(report["source"])
    if report["data_classification"] not in VALID_DATA_CLASSIFICATIONS:
        raise ValueError("Field 'data_classification' is invalid.")
    source_profile = SOURCE_PROFILE[report["source"]["source_type"]]
    if report["data_classification"] != source_profile["data_classification"]:
        raise ValueError("Field 'data_classification' does not match source profile.")

    restore_tests = report["restore_tests"]
    if not isinstance(restore_tests, list) or not restore_tests:
        raise ValueError("Field 'restore_tests' must be a non-empty list.")

    restore_test_ids = [
        _validate_restore_test(
            restore_test,
            index,
            source_profile["collection_method"],
        )
        for index, restore_test in enumerate(restore_tests)
    ]
    if len(set(restore_test_ids)) != len(restore_test_ids):
        raise ValueError("Restore-test identifiers must be unique.")

    normalized = deepcopy(report)
    normalized["restore_tests"].sort(key=lambda item: item["restore_test_id"])
    return normalized


def load_restore_test_evidence(path: Path) -> dict:
    """Load and validate one local restore-test evidence JSON file."""
    with path.open(encoding="utf-8") as report_file:
        return validate_restore_test_evidence(json.load(report_file))
