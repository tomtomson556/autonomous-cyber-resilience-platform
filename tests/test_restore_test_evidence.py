import ast
import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.tools.restore_test_evidence import (
    REPORT_TYPE,
    SCHEMA_VERSION,
    load_restore_test_evidence,
    validate_restore_test_evidence,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIRECTORY = PROJECT_ROOT / "tests" / "fixtures" / "restore_test_evidence"
MODULE_PATH = PROJECT_ROOT / "src" / "tools" / "restore_test_evidence.py"


def load_fixture(name: str) -> dict:
    with (FIXTURE_DIRECTORY / name).open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def test_fixtures_are_sanitized_and_contain_no_external_references():
    prohibited_markers = (
        "://",
        "credential",
        "customer",
        "hostname",
        "password",
        "secret",
        "token",
    )

    for fixture_path in FIXTURE_DIRECTORY.glob("*.json"):
        content = fixture_path.read_text(encoding="utf-8").lower()
        assert all(marker not in content for marker in prohibited_markers)


@pytest.mark.parametrize(
    ("fixture_name", "expected_result"),
    [
        ("valid_pass.json", "PASS"),
        ("valid_fail.json", "FAIL"),
        ("valid_unknown.json", "UNKNOWN"),
    ],
)
def test_valid_evidence_fixtures_are_accepted(fixture_name, expected_result):
    report = load_restore_test_evidence(FIXTURE_DIRECTORY / fixture_name)

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["report_type"] == REPORT_TYPE
    assert report["restore_tests"][0]["result"] == expected_result


@pytest.mark.parametrize(
    ("fixture_name", "message"),
    [
        ("invalid_missing_required_field.json", "containing exactly"),
        ("invalid_non_utc_timestamp.json", "must be a UTC timestamp"),
        ("invalid_duration_mismatch.json", "does not match timestamps"),
    ],
)
def test_invalid_evidence_fixtures_are_rejected(fixture_name, message):
    with pytest.raises(ValueError, match=message):
        load_restore_test_evidence(FIXTURE_DIRECTORY / fixture_name)


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("schema_version", "restore-test-evidence/v2", "Unsupported"),
        ("report_type", "restore_test", "report_type must be"),
        ("data_classification", "SECRET", "data_classification"),
    ],
)
def test_invalid_top_level_contract_values_are_rejected(field_name, value, message):
    report = load_fixture("valid_pass.json")
    report[field_name] = value

    with pytest.raises(ValueError, match=message):
        validate_restore_test_evidence(report)


def test_invalid_source_type_is_rejected():
    report = load_fixture("valid_pass.json")
    report["source"]["source_type"] = "direct_api"

    with pytest.raises(ValueError, match="source.source_type.*invalid"):
        validate_restore_test_evidence(report)


def test_unknown_evidence_with_complete_consistent_timing_is_valid():
    report = load_fixture("valid_pass.json")
    report["restore_tests"][0]["result"] = "UNKNOWN"
    report["restore_tests"][0]["reason"] = "ValidationInconclusive"
    report["restore_tests"][0]["validation"]["status"] = "UNKNOWN"

    result = validate_restore_test_evidence(report)

    assert result["restore_tests"][0]["result"] == "UNKNOWN"
    assert result["restore_tests"][0]["duration_seconds"] == 600


@pytest.mark.parametrize(
    ("source_type", "classification", "collection_method"),
    [
        (
            "manual_attestation",
            "SANITIZED_OPERATIONAL_EVIDENCE",
            "manual_import",
        ),
        (
            "external_test_record",
            "SANITIZED_OPERATIONAL_EVIDENCE",
            "external_record_import",
        ),
    ],
)
def test_sanitized_operational_source_profiles_are_valid(
    source_type,
    classification,
    collection_method,
):
    report = load_fixture("valid_pass.json")
    report["source"]["source_type"] = source_type
    report["data_classification"] = classification
    report["restore_tests"][0]["provenance"]["collection_method"] = collection_method
    report["restore_tests"][0]["validation"]["method"] = source_type

    result = validate_restore_test_evidence(report)

    assert result["source"]["source_type"] == source_type


def test_source_profile_classification_mismatch_is_rejected():
    report = load_fixture("valid_pass.json")
    report["data_classification"] = "SANITIZED_OPERATIONAL_EVIDENCE"

    with pytest.raises(ValueError, match="data_classification.*source profile"):
        validate_restore_test_evidence(report)


def test_source_profile_collection_method_mismatch_is_rejected():
    report = load_fixture("valid_pass.json")
    report["restore_tests"][0]["provenance"]["collection_method"] = "manual_import"

    with pytest.raises(ValueError, match="collection_method.*source profile"):
        validate_restore_test_evidence(report)


@pytest.mark.parametrize("result", ["PASS", "FAIL"])
def test_pass_or_fail_without_timing_is_rejected(result):
    report = load_fixture("valid_unknown.json")
    report["restore_tests"][0]["result"] = result

    with pytest.raises(ValueError, match="PASS/FAIL timing is required"):
        validate_restore_test_evidence(report)


def test_partial_timing_is_rejected():
    report = load_fixture("valid_unknown.json")
    report["restore_tests"][0]["started_at"] = "2026-06-12T12:00:00Z"

    with pytest.raises(ValueError, match="timing must be complete"):
        validate_restore_test_evidence(report)


@pytest.mark.parametrize("duration", [-1, True, 1.5])
def test_negative_boolean_or_non_integer_duration_is_rejected(duration):
    report = load_fixture("valid_pass.json")
    report["restore_tests"][0]["duration_seconds"] = duration

    with pytest.raises(ValueError, match="duration_seconds.*non-negative"):
        validate_restore_test_evidence(report)


def test_completion_before_start_is_rejected():
    report = load_fixture("valid_pass.json")
    report["restore_tests"][0]["completed_at"] = "2026-06-12T11:59:00Z"
    report["restore_tests"][0]["duration_seconds"] = 60

    with pytest.raises(ValueError, match="precedes started_at"):
        validate_restore_test_evidence(report)


def test_fractional_timestamp_duration_mismatch_is_rejected():
    report = load_fixture("valid_pass.json")
    report["restore_tests"][0]["completed_at"] = "2026-06-12T12:10:00.500000Z"

    with pytest.raises(ValueError, match="does not match timestamps"):
        validate_restore_test_evidence(report)


def test_provenance_collected_after_report_generation_is_rejected():
    report = load_fixture("valid_pass.json")
    report["restore_tests"][0]["provenance"]["collected_at"] = (
        "2026-06-12T12:31:00Z"
    )

    with pytest.raises(ValueError, match="collected_at.*must not be after generated_at"):
        validate_restore_test_evidence(report)


def test_completion_after_provenance_collection_is_rejected():
    report = load_fixture("valid_pass.json")
    report["restore_tests"][0]["provenance"]["collected_at"] = (
        "2026-06-12T12:09:00Z"
    )

    with pytest.raises(
        ValueError,
        match="completed_at.*must not be after.*provenance.collected_at",
    ):
        validate_restore_test_evidence(report)


def test_valid_complete_timestamp_chain_is_accepted():
    report = load_fixture("valid_pass.json")

    result = validate_restore_test_evidence(report)

    restore_test = result["restore_tests"][0]
    assert restore_test["started_at"] <= restore_test["completed_at"]
    assert (
        restore_test["completed_at"]
        <= restore_test["validation"]["checked_at"]
        <= restore_test["provenance"]["collected_at"]
        <= result["generated_at"]
    )


def test_unknown_without_completion_remains_valid_when_collection_precedes_generation():
    report = load_fixture("valid_unknown.json")

    result = validate_restore_test_evidence(report)

    assert result["restore_tests"][0]["completed_at"] is None
    assert result["restore_tests"][0]["provenance"]["collected_at"] <= result["generated_at"]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("result", "SUCCESS"),
        ("restore_scope", "production_disaster_recovery"),
        ("restore_target_type", "production"),
    ],
)
def test_unapproved_result_scope_or_target_is_rejected(field_name, value):
    report = load_fixture("valid_pass.json")
    report["restore_tests"][0][field_name] = value

    with pytest.raises(ValueError, match=f"{field_name}'.*invalid"):
        validate_restore_test_evidence(report)


@pytest.mark.parametrize(
    ("location", "field_name", "value"),
    [
        ("report", "password", "blocked"),
        ("source", "endpoint", "blocked"),
        ("restore_test", "token", "blocked"),
        ("provenance", "hostname", "blocked"),
        ("validation", "connection", "blocked"),
    ],
)
def test_closed_objects_reject_auth_network_and_secret_fields(
    location,
    field_name,
    value,
):
    report = load_fixture("valid_pass.json")
    targets = {
        "report": report,
        "source": report["source"],
        "restore_test": report["restore_tests"][0],
        "provenance": report["restore_tests"][0]["provenance"],
        "validation": report["restore_tests"][0]["validation"],
    }
    targets[location][field_name] = value

    with pytest.raises(ValueError, match="containing exactly"):
        validate_restore_test_evidence(report)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("source", "source_id"), "https://example.invalid/source"),
        (
            ("restore_tests", 0, "source_backup_reference"),
            "token-example-001",
        ),
        (
            ("restore_tests", 0, "provenance", "source_record_id"),
            "credential-example-001",
        ),
        (("restore_tests", 0, "source_system"), "internal.example.local"),
        (
            ("restore_tests", 0, "validation", "evidence_reference"),
            "secret-validation-record",
        ),
    ],
)
def test_references_must_be_sanitized(path, value):
    report = load_fixture("valid_pass.json")
    target = report
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value

    with pytest.raises(ValueError, match="sanitized local reference"):
        validate_restore_test_evidence(report)


def test_duplicate_restore_test_ids_are_rejected():
    report = load_fixture("valid_pass.json")
    report["restore_tests"].append(deepcopy(report["restore_tests"][0]))

    with pytest.raises(ValueError, match="identifiers must be unique"):
        validate_restore_test_evidence(report)


def test_duplicate_source_evidence_is_rejected_for_different_restore_test_ids():
    report = load_fixture("valid_pass.json")
    second = deepcopy(report["restore_tests"][0])
    second["restore_test_id"] = "restore-test-pass-002"
    report["restore_tests"].append(second)

    with pytest.raises(ValueError, match="source evidence references.*must be unique"):
        validate_restore_test_evidence(report)


def test_different_source_record_ids_are_allowed():
    report = load_fixture("valid_pass.json")
    second = deepcopy(report["restore_tests"][0])
    second["restore_test_id"] = "restore-test-pass-002"
    second["provenance"]["source_record_id"] = "fixture-record-pass-002"
    report["restore_tests"].append(second)

    result = validate_restore_test_evidence(report)

    assert len(result["restore_tests"]) == 2


def test_restore_tests_are_sorted_deterministically_without_mutating_input():
    report = load_fixture("valid_pass.json")
    second = deepcopy(report["restore_tests"][0])
    second["restore_test_id"] = "restore-test-a-001"
    second["asset_id"] = "asset-example-a"
    second["source_backup_reference"] = "backup-example-a"
    second["provenance"]["source_record_id"] = "fixture-record-a-001"
    report["restore_tests"].append(second)
    original = deepcopy(report)

    first_result = validate_restore_test_evidence(report)
    second_result = validate_restore_test_evidence(report)

    assert first_result == second_result
    assert [
        restore_test["restore_test_id"]
        for restore_test in first_result["restore_tests"]
    ] == ["restore-test-a-001", "restore-test-pass-001"]
    assert report == original


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("generated_at", "2026-06-12T12:30:00"),
        ("generated_at", "2026-06-12T13:30:00+01:00"),
    ],
)
def test_top_level_timestamp_must_be_utc(field_name, value):
    report = load_fixture("valid_pass.json")
    report[field_name] = value

    with pytest.raises(ValueError, match="UTC timestamp"):
        validate_restore_test_evidence(report)


def test_provenance_timestamp_must_be_utc():
    report = load_fixture("valid_pass.json")
    report["restore_tests"][0]["provenance"]["collected_at"] = (
        "2026-06-12T13:20:00+01:00"
    )

    with pytest.raises(ValueError, match="UTC timestamp"):
        validate_restore_test_evidence(report)


@pytest.mark.parametrize(
    "path",
    [
        ("restore_tests", 0, "reason"),
        ("restore_tests", 0, "message"),
        ("source", "source_id"),
        ("restore_tests", 0, "restore_test_id"),
        ("restore_tests", 0, "provenance", "source_record_id"),
        ("restore_tests", 0, "validation", "evidence_reference"),
    ],
)
def test_whitespace_only_strings_are_rejected(path):
    report = load_fixture("valid_pass.json")
    target = report
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = "   "

    with pytest.raises(ValueError, match="non-empty string"):
        validate_restore_test_evidence(report)


@pytest.mark.parametrize(
    ("result", "validation_status", "message"),
    [
        ("PASS", "FAILED", "must be 'VERIFIED' for result 'PASS'"),
        ("FAIL", "VERIFIED", "must be 'FAILED' for result 'FAIL'"),
        ("UNKNOWN", "VERIFIED", "must be 'UNKNOWN' for result 'UNKNOWN'"),
    ],
)
def test_result_requires_matching_structured_validation_status(
    result,
    validation_status,
    message,
):
    report = load_fixture("valid_pass.json")
    report["restore_tests"][0]["result"] = result
    report["restore_tests"][0]["validation"]["status"] = validation_status

    with pytest.raises(ValueError, match=message):
        validate_restore_test_evidence(report)


def test_validation_method_must_match_source_profile():
    report = load_fixture("valid_pass.json")
    report["restore_tests"][0]["validation"]["method"] = "manual_attestation"

    with pytest.raises(ValueError, match="validation.method.*source profile"):
        validate_restore_test_evidence(report)


@pytest.mark.parametrize("field_name", ["checked_at", "evidence_reference"])
def test_pass_requires_complete_structured_validation_evidence(field_name):
    report = load_fixture("valid_pass.json")
    report["restore_tests"][0]["validation"][field_name] = None

    with pytest.raises(ValueError, match=f"validation.{field_name}"):
        validate_restore_test_evidence(report)


def test_validation_checked_at_must_be_utc():
    report = load_fixture("valid_pass.json")
    report["restore_tests"][0]["validation"]["checked_at"] = (
        "2026-06-12T13:15:00+01:00"
    )

    with pytest.raises(ValueError, match="validation.checked_at.*UTC timestamp"):
        validate_restore_test_evidence(report)


def test_validation_checked_at_before_completion_is_rejected():
    report = load_fixture("valid_pass.json")
    report["restore_tests"][0]["validation"]["checked_at"] = "2026-06-12T12:09:00Z"

    with pytest.raises(ValueError, match="validation.checked_at.*must not precede"):
        validate_restore_test_evidence(report)


def test_validation_checked_at_after_collection_is_rejected():
    report = load_fixture("valid_pass.json")
    report["restore_tests"][0]["validation"]["checked_at"] = "2026-06-12T12:21:00Z"

    with pytest.raises(ValueError, match="validation.checked_at.*must not be after"):
        validate_restore_test_evidence(report)


def test_module_has_no_network_or_external_client_imports():
    syntax_tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported_roots = {
        alias.name.split(".")[0]
        for node in ast.walk(syntax_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        node.module.split(".")[0]
        for node in ast.walk(syntax_tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )

    assert imported_roots.isdisjoint(
        {"aiohttp", "boto3", "httpx", "paramiko", "requests", "socket", "urllib"}
    )


def test_module_exposes_no_restore_execution_or_external_connection_hooks():
    syntax_tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    function_names = {
        node.name.lower()
        for node in ast.walk(syntax_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert function_names.isdisjoint(
        {
            "connect",
            "execute_restore",
            "run_restore",
            "start_job",
            "write_remote",
        }
    )
