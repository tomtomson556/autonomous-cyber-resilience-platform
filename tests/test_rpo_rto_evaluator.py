import ast
import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.tools.rpo_rto_evaluator import (
    EVALUATION_SCHEMA_VERSION,
    POLICY_SCHEMA_VERSION,
    evaluate_report,
    load_policy,
    main,
    validate_policy,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVALUATOR_PATH = PROJECT_ROOT / "src" / "tools" / "rpo_rto_evaluator.py"
RESTORE_FIXTURE_DIRECTORY = PROJECT_ROOT / "tests" / "fixtures" / "restore_test_evidence"
EVALUATION_TIMESTAMP = "2026-06-12T12:00:00+00:00"
RTO_EVALUATION_TIMESTAMP = "2026-06-12T13:00:00+00:00"


def policy(
    *asset_ids: str,
    evaluation_timestamp: str | None = EVALUATION_TIMESTAMP,
    include_rto: bool = False,
) -> dict:
    result = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "report_type": "rpo_rto_policy",
        "rules": [
            {
                "policy_id": f"policy-{asset_id}",
                "asset_id": asset_id,
                "rpo_objective_minutes": 120,
                **({"rto_objective_minutes": 60} if include_rto else {}),
            }
            for asset_id in asset_ids
        ],
    }
    if evaluation_timestamp is not None:
        result["evaluation_timestamp"] = evaluation_timestamp
    return result


def backup_asset(
    asset_id: str,
    *,
    timestamp: object = "2026-06-12T11:00:00+00:00",
    status: object = "PASS",
) -> dict:
    details = {
        "job_id": f"job-{asset_id}",
        "last_successful_backup": timestamp,
    }
    return {
        "asset_id": asset_id,
        "source_type": "veeam",
        "backup_system": "veeam",
        "resource_type": "backup_job",
        "evidence_source_id": f"source-{asset_id}",
        "source_evidence": {
            "status": status,
            "reason": "TestEvidence",
            "message": "Test backup evidence.",
            "collected_at": EVALUATION_TIMESTAMP,
            "details": details,
        },
        "risk_score": None,
        "recommended_action": None,
    }


def unified_report(*assets: dict) -> dict:
    return {
        "schema_version": "1.0.0",
        "timestamp": EVALUATION_TIMESTAMP,
        "platform": "autonomous-cyber-resilience-platform",
        "report_type": "unified_resilience_report",
        "data_classification": "MOCK_EXAMPLE_ONLY",
        "overall_resilience_status": "HEALTHY",
        "evidence_sources": [
            {
                "source_id": asset.get("evidence_source_id", f"source-{index}"),
                "source_type": "test",
                "collected_at": EVALUATION_TIMESTAMP,
                "status": "PASS",
                "reference": f"mock://source-{index}",
            }
            for index, asset in enumerate(assets)
        ],
        "assets": list(assets),
        "findings": [],
        "recommended_actions": [],
    }


def result_for(report: dict, input_policy: dict | None = None) -> dict:
    asset_id = input_policy["rules"][0]["asset_id"] if input_policy else report["assets"][0]["asset_id"]
    evaluation = evaluate_report(report, input_policy or policy(asset_id))
    return evaluation["asset_results"][0]["evaluations"][0]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def restore_test_evidence(fixture_name: str, asset_id: str = "asset-a") -> dict:
    with (RESTORE_FIXTURE_DIRECTORY / fixture_name).open(encoding="utf-8") as fixture:
        evidence = json.load(fixture)
    evidence["restore_tests"][0]["asset_id"] = asset_id
    return evidence


def rto_result(
    evidence: dict | None,
    *,
    asset_id: str = "asset-a",
    evaluation_timestamp: str = RTO_EVALUATION_TIMESTAMP,
) -> tuple[dict, dict]:
    input_policy = policy(
        asset_id,
        evaluation_timestamp=evaluation_timestamp,
        include_rto=True,
    )
    evaluation = evaluate_report(
        unified_report(backup_asset(asset_id)),
        input_policy,
        restore_test_evidence=evidence,
    )
    results = {
        result["objective_type"]: result
        for result in evaluation["asset_results"][0]["evaluations"]
    }
    return results["RTO"], results["RPO"]


def test_valid_policy_is_accepted_and_loadable(tmp_path):
    input_policy = policy("asset-a")
    path = tmp_path / "policy.json"
    write_json(path, input_policy)

    validate_policy(input_policy)

    assert load_policy(path) == input_policy


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.pop("schema_version"), "missing required fields"),
        (
            lambda value: value.update(schema_version="rpo-rto-policy/v2"),
            "Unsupported RPO/RTO policy schema_version",
        ),
        (lambda value: value["rules"][0].pop("asset_id"), "missing required fields"),
        (
            lambda value: value["rules"][0].update(rpo_objective_minutes=0),
            "positive integer",
        ),
        (
            lambda value: value["rules"][0].update(rpo_objective_minutes="120"),
            "positive integer",
        ),
        (
            lambda value: value["rules"][0].update(rto_objective_minutes=0),
            "positive integer",
        ),
    ],
)
def test_invalid_policy_contract_is_rejected(mutation, message):
    input_policy = policy("asset-a")
    mutation(input_policy)

    with pytest.raises(ValueError, match=message):
        validate_policy(input_policy)


def test_duplicate_policy_ids_are_rejected():
    input_policy = policy("asset-a", "asset-b")
    input_policy["rules"][1]["policy_id"] = input_policy["rules"][0]["policy_id"]

    with pytest.raises(ValueError, match="Duplicate policy_id"):
        validate_policy(input_policy)


def test_duplicate_asset_objectives_are_rejected():
    input_policy = policy("asset-a", "asset-b")
    input_policy["rules"][1]["asset_id"] = "asset-a"

    with pytest.raises(ValueError, match="Duplicate RPO objective"):
        validate_policy(input_policy)


@pytest.mark.parametrize(
    ("location", "field_name"),
    [
        ("top", "password"),
        ("top", "network"),
        ("top", "auth"),
        ("rule", "key"),
        ("rule", "token"),
        ("rule", "url"),
        ("rule", "host"),
        ("rule", "port"),
        ("rule", "credential"),
        ("rule", "connection_string"),
    ],
)
def test_policy_rejects_secret_auth_and_connection_fields(location, field_name):
    input_policy = policy("asset-a")
    target = input_policy if location == "top" else input_policy["rules"][0]
    target[field_name] = "not-allowed"

    with pytest.raises(ValueError, match="unsupported fields"):
        validate_policy(input_policy)


def test_missing_evaluation_timestamp_is_rejected():
    with pytest.raises(ValueError, match="explicit evaluation timestamp"):
        evaluate_report(
            unified_report(backup_asset("asset-a")),
            policy("asset-a", evaluation_timestamp=None),
        )


@pytest.mark.parametrize(
    "timestamp",
    ["not-a-timestamp", "2026-06-12T12:00:00", "2026-06-12T13:00:00+01:00"],
)
def test_invalid_or_non_utc_evaluation_timestamp_is_rejected(timestamp):
    with pytest.raises(ValueError, match="evaluation_timestamp"):
        evaluate_report(
            unified_report(backup_asset("asset-a")),
            policy("asset-a", evaluation_timestamp=timestamp),
        )


def test_explicit_evaluation_timestamp_overrides_policy_timestamp():
    input_policy = policy("asset-a", evaluation_timestamp="2026-06-12T10:00:00Z")

    result = evaluate_report(
        unified_report(backup_asset("asset-a")),
        input_policy,
        EVALUATION_TIMESTAMP,
    )

    assert result["evaluation_timestamp"] == EVALUATION_TIMESTAMP


@pytest.mark.parametrize(
    ("backup_timestamp", "expected_status", "expected_reason", "expected_age"),
    [
        ("2026-06-12T11:00:00+00:00", "PASS", "RPO_WITHIN_OBJECTIVE", 60),
        ("2026-06-12T10:00:00+00:00", "PASS", "RPO_WITHIN_OBJECTIVE", 120),
        ("2026-06-12T09:59:00+00:00", "FAIL", "RPO_EXCEEDED", 121),
    ],
)
def test_rpo_boundary_behavior(
    backup_timestamp,
    expected_status,
    expected_reason,
    expected_age,
):
    result = result_for(unified_report(backup_asset("asset-a", timestamp=backup_timestamp)))

    assert result["status"] == expected_status
    assert result["reason"] == expected_reason
    assert result["observed_age_minutes"] == expected_age


@pytest.mark.parametrize(
    ("timestamp", "expected_reason"),
    [
        (None, "MISSING_BACKUP_EVIDENCE"),
        ("not-a-timestamp", "INVALID_BACKUP_TIMESTAMP"),
        ("2026-06-12T11:00:00", "NON_UTC_BACKUP_TIMESTAMP"),
        ("2026-06-12T13:00:00+00:00", "FUTURE_BACKUP_TIMESTAMP"),
    ],
)
def test_unusable_backup_timestamps_produce_unknown(timestamp, expected_reason):
    result = result_for(unified_report(backup_asset("asset-a", timestamp=timestamp)))

    assert result["status"] == "UNKNOWN"
    assert result["reason"] == expected_reason
    assert result["observed_age_minutes"] is None


@pytest.mark.parametrize("status", ["UNKNOWN", "FAIL", None])
def test_non_pass_backup_evidence_is_not_used(status):
    result = result_for(unified_report(backup_asset("asset-a", status=status)))

    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "MISSING_BACKUP_EVIDENCE"


def test_missing_backup_evidence_produces_unknown():
    asset = backup_asset("asset-a")
    del asset["source_evidence"]

    result = result_for(unified_report(asset))

    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "MISSING_BACKUP_EVIDENCE"


def test_backup_evidence_on_another_asset_is_not_correlated():
    workload = {
        "asset_id": "workload-a",
        "source_type": "m365",
        "backup_system": "veeam",
        "risk_score": None,
        "recommended_action": None,
    }
    report = unified_report(workload, backup_asset("backup-job-a"))

    result = result_for(report, policy("workload-a"))

    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "MISSING_BACKUP_EVIDENCE"


def test_missing_source_relationship_produces_unknown():
    asset = backup_asset("asset-a")
    asset["evidence_source_id"] = "source-not-in-report"
    report = unified_report(asset)
    report["evidence_sources"][0]["source_id"] = "different-source"

    result = result_for(report)

    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "UNLINKED_BACKUP_EVIDENCE"


def test_ambiguous_direct_backup_evidence_produces_unknown():
    asset = backup_asset("asset-a")
    asset["backup_job"] = {
        "status": "PASS",
        "last_successful_backup": "2026-06-12T11:00:00+00:00",
    }

    result = result_for(unified_report(asset))

    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "AMBIGUOUS_BACKUP_EVIDENCE"


def test_missing_asset_produces_unknown():
    result = result_for(
        unified_report(backup_asset("asset-a")),
        policy("missing-asset"),
    )

    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "MISSING_ASSET"


def test_embedded_direct_backup_job_can_be_evaluated():
    asset = {
        "asset_id": "workload-a",
        "source_type": "m365",
        "backup_system": "veeam",
        "backup_job": {
            "status": "PASS",
            "last_successful_backup": "2026-06-12T11:00:00Z",
            "source_id": "source-backup-a",
        },
        "risk_score": None,
        "recommended_action": None,
    }
    report = unified_report(asset)
    report["evidence_sources"][0]["source_id"] = "source-backup-a"

    result = result_for(report)

    assert result["status"] == "PASS"
    assert result["source_evidence_ids"] == ["source-backup-a"]


def test_embedded_backup_job_with_unlinked_source_produces_unknown():
    asset = {
        "asset_id": "workload-a",
        "source_type": "m365",
        "backup_system": "veeam",
        "backup_job": {
            "status": "PASS",
            "last_successful_backup": "2026-06-12T11:00:00Z",
            "source_id": "source-not-in-report",
        },
        "risk_score": None,
        "recommended_action": None,
    }

    result = result_for(unified_report(asset))

    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "UNLINKED_BACKUP_EVIDENCE"


def test_rto_without_explicit_evidence_does_not_interpret_unified_restore_fields():
    asset = backup_asset("asset-a")
    asset["restore_point"] = {"status": "PASS"}
    asset["restore_test_evidence"] = {
        "status": "PASS",
        "observed_recovery_minutes": 1,
    }
    asset["successful_backup_session"] = {"status": "PASS"}

    evaluation = evaluate_report(
        unified_report(asset),
        policy("asset-a", include_rto=True),
    )
    results = {
        result["objective_type"]: result
        for result in evaluation["asset_results"][0]["evaluations"]
    }

    assert results["RPO"]["status"] == "PASS"
    assert results["RTO"]["status"] == "UNKNOWN"
    assert results["RTO"]["reason"] == "RTO_EVIDENCE_CONTRACT_NOT_AVAILABLE"
    assert results["RTO"]["source_evidence_ids"] == []


def test_rto_passes_from_validated_restore_test_within_objective():
    result, rpo_result_value = rto_result(
        restore_test_evidence("valid_pass.json"),
    )

    assert result == {
        "evaluation_id": result["evaluation_id"],
        "objective_type": "RTO",
        "objective_minutes": 60,
        "observed_recovery_minutes": 10,
        "status": "PASS",
        "reason": "RTO_WITHIN_OBJECTIVE",
        "message": "The validated restore test completed within the RTO objective.",
        "restore_test_id": "restore-test-pass-001",
        "source_evidence_ids": [
            "backup-example-001",
            "fixture-record-pass-001",
            "fixture-source-pass",
            "fixture-validation-pass-001",
        ],
    }
    assert rpo_result_value["status"] == "PASS"


def test_rto_fails_when_validated_pass_restore_test_exceeds_objective():
    evidence = restore_test_evidence("valid_pass.json")
    restore_test = evidence["restore_tests"][0]
    restore_test["started_at"] = "2026-06-12T11:00:00+00:00"
    restore_test["completed_at"] = "2026-06-12T12:10:00+00:00"
    restore_test["duration_seconds"] = 4200

    result, _ = rto_result(evidence)

    assert result["status"] == "FAIL"
    assert result["reason"] == "RTO_EXCEEDED_OBJECTIVE"
    assert result["observed_recovery_minutes"] == 70


def test_rto_passes_at_exact_seconds_to_minutes_objective_boundary():
    evidence = restore_test_evidence("valid_pass.json")
    restore_test = evidence["restore_tests"][0]
    restore_test["started_at"] = "2026-06-12T11:10:00+00:00"
    restore_test["completed_at"] = "2026-06-12T12:10:00+00:00"
    restore_test["duration_seconds"] = 3600

    result, _ = rto_result(evidence)

    assert result["status"] == "PASS"
    assert result["reason"] == "RTO_WITHIN_OBJECTIVE"
    assert result["observed_recovery_minutes"] == 60


def test_rto_fails_when_structured_restore_test_result_is_fail():
    result, _ = rto_result(restore_test_evidence("valid_fail.json"))

    assert result["status"] == "FAIL"
    assert result["reason"] == "RTO_RESTORE_TEST_FAILED"
    assert result["observed_recovery_minutes"] == 5


def test_rto_unknown_without_restore_test_evidence_preserves_compatible_output():
    result, _ = rto_result(None)

    assert result == {
        "objective_type": "RTO",
        "objective_minutes": 60,
        "observed_recovery_minutes": None,
        "status": "UNKNOWN",
        "reason": "RTO_EVIDENCE_CONTRACT_NOT_AVAILABLE",
        "message": (
            "RTO cannot be evaluated until a separate versioned restore-test "
            "evidence contract exists."
        ),
        "source_evidence_ids": [],
        "evaluation_id": "evaluation-7cc7e7aca58cf7f6cf04",
    }


def test_rto_unknown_for_structured_unknown_restore_test():
    result, _ = rto_result(restore_test_evidence("valid_unknown.json"))

    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "RTO_RESTORE_TEST_UNKNOWN"
    assert result["restore_test_id"] == "restore-test-unknown-001"
    assert result["observed_recovery_minutes"] is None


def test_rto_unknown_for_multiple_reliable_restore_tests():
    evidence = restore_test_evidence("valid_pass.json")
    second = deepcopy(evidence["restore_tests"][0])
    second["restore_test_id"] = "restore-test-pass-002"
    second["source_backup_reference"] = "backup-example-002"
    second["provenance"]["source_record_id"] = "fixture-record-pass-002"
    second["validation"]["evidence_reference"] = "fixture-validation-pass-002"
    evidence["restore_tests"].append(second)

    result, _ = rto_result(evidence)

    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "RTO_RESTORE_TEST_AMBIGUOUS"
    assert "restore_test_id" not in result
    assert "fixture-record-pass-002" in result["source_evidence_ids"]


def test_restore_test_for_another_asset_is_not_used():
    result, _ = rto_result(
        restore_test_evidence("valid_pass.json", asset_id="asset-other"),
    )

    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "RTO_RESTORE_TEST_ASSET_NOT_FOUND"
    assert result["source_evidence_ids"] == []


def test_rto_unknown_when_restore_test_report_has_future_timestamp():
    result, _ = rto_result(
        restore_test_evidence("valid_pass.json"),
        evaluation_timestamp="2026-06-12T12:25:00+00:00",
    )

    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "RTO_RESTORE_TEST_FUTURE_TIMESTAMP"
    assert result["restore_test_id"] == "restore-test-pass-001"


def test_invalid_restore_test_evidence_fails_closed():
    evidence = restore_test_evidence("valid_pass.json")
    evidence["restore_tests"][0]["duration_seconds"] = 1

    with pytest.raises(ValueError, match="duration_seconds.*does not match"):
        rto_result(evidence)


def test_rto_ignores_restore_test_free_text_for_decision():
    evidence = restore_test_evidence("valid_pass.json")
    evidence["restore_tests"][0]["reason"] = "ClaimsFailure"
    evidence["restore_tests"][0]["message"] = "Claims that the objective was exceeded."

    result, _ = rto_result(evidence)

    assert result["status"] == "PASS"
    assert result["reason"] == "RTO_WITHIN_OBJECTIVE"


def test_restore_test_evidence_produces_stable_output_ids_and_input_reference():
    evidence = restore_test_evidence("valid_pass.json")
    report = unified_report(backup_asset("asset-a"))
    input_policy = policy(
        "asset-a",
        evaluation_timestamp=RTO_EVALUATION_TIMESTAMP,
        include_rto=True,
    )

    first = evaluate_report(report, input_policy, restore_test_evidence=evidence)
    second = evaluate_report(report, input_policy, restore_test_evidence=evidence)

    assert first == second
    assert first["restore_test_evidence"]["reference"].startswith(
        "restore-test-evidence:sha256:"
    )


def test_rto_evaluation_id_changes_with_restore_evidence_and_observed_duration():
    first_evidence = restore_test_evidence("valid_pass.json")
    second_evidence = deepcopy(first_evidence)
    second_restore_test = second_evidence["restore_tests"][0]
    second_restore_test["started_at"] = "2026-06-12T11:50:00+00:00"
    second_restore_test["duration_seconds"] = 1200
    report = unified_report(backup_asset("asset-a"))
    input_policy = policy(
        "asset-a",
        evaluation_timestamp=RTO_EVALUATION_TIMESTAMP,
        include_rto=True,
    )

    first = evaluate_report(
        report,
        input_policy,
        restore_test_evidence=first_evidence,
    )
    second = evaluate_report(
        report,
        input_policy,
        restore_test_evidence=second_evidence,
    )
    first_rto = first["asset_results"][0]["evaluations"][1]
    second_rto = second["asset_results"][0]["evaluations"][1]

    assert first_rto["restore_test_id"] == second_rto["restore_test_id"]
    assert first_rto["source_evidence_ids"] == second_rto["source_evidence_ids"]
    assert first_rto["observed_recovery_minutes"] == 10
    assert second_rto["observed_recovery_minutes"] == 20
    assert first["restore_test_evidence"]["reference"] != (
        second["restore_test_evidence"]["reference"]
    )
    assert first_rto["evaluation_id"] != second_rto["evaluation_id"]


def test_restore_test_order_does_not_change_output_or_evaluation_ids():
    evidence = restore_test_evidence("valid_pass.json", asset_id="asset-a")
    second = deepcopy(evidence["restore_tests"][0])
    second["restore_test_id"] = "restore-test-pass-002"
    second["asset_id"] = "asset-b"
    second["source_backup_reference"] = "backup-example-002"
    second["provenance"]["source_record_id"] = "fixture-record-pass-002"
    second["validation"]["evidence_reference"] = "fixture-validation-pass-002"
    evidence["restore_tests"].append(second)
    reversed_evidence = deepcopy(evidence)
    reversed_evidence["restore_tests"].reverse()
    report = unified_report(backup_asset("asset-b"), backup_asset("asset-a"))
    input_policy = policy(
        "asset-b",
        "asset-a",
        evaluation_timestamp=RTO_EVALUATION_TIMESTAMP,
        include_rto=True,
    )

    first = evaluate_report(report, input_policy, restore_test_evidence=evidence)
    reordered = evaluate_report(
        report,
        input_policy,
        restore_test_evidence=reversed_evidence,
    )

    assert first == reordered
    assert [result["asset_id"] for result in first["asset_results"]] == [
        "asset-a",
        "asset-b",
    ]


def test_restore_test_evidence_does_not_change_rpo_result():
    report = unified_report(backup_asset("asset-a"))
    input_policy = policy(
        "asset-a",
        evaluation_timestamp=RTO_EVALUATION_TIMESTAMP,
        include_rto=True,
    )

    without_evidence = evaluate_report(report, input_policy)
    with_evidence = evaluate_report(
        report,
        input_policy,
        restore_test_evidence=restore_test_evidence("valid_pass.json"),
    )

    assert without_evidence["asset_results"][0]["evaluations"][0] == (
        with_evidence["asset_results"][0]["evaluations"][0]
    )


def test_output_is_separate_and_input_objects_are_not_mutated():
    report = unified_report(backup_asset("asset-a"))
    input_policy = policy("asset-a", include_rto=True)
    original_report = deepcopy(report)
    original_policy = deepcopy(input_policy)

    result = evaluate_report(report, input_policy)

    assert result["schema_version"] == EVALUATION_SCHEMA_VERSION
    assert result["report_type"] == "resilience_evaluation_report"
    assert "findings" not in result
    assert report == original_report
    assert input_policy == original_policy


def test_repeated_runs_and_rule_order_produce_stable_output_and_ids():
    report = unified_report(backup_asset("asset-a"), backup_asset("asset-b"))
    forward_policy = policy("asset-b", "asset-a", include_rto=True)
    reverse_policy = deepcopy(forward_policy)
    reverse_policy["rules"].reverse()

    first = evaluate_report(report, forward_policy)
    second = evaluate_report(report, forward_policy)
    reordered = evaluate_report(report, reverse_policy)

    assert first == second
    assert first == reordered
    assert [item["asset_id"] for item in first["asset_results"]] == [
        "asset-a",
        "asset-b",
    ]
    assert all(
        result["evaluation_id"].startswith("evaluation-")
        for asset_result in first["asset_results"]
        for result in asset_result["evaluations"]
    )


def test_invalid_unified_report_is_rejected():
    report = unified_report(backup_asset("asset-a"))
    report["schema_version"] = "2.0.0"

    with pytest.raises(ValueError, match="Unsupported Unified"):
        evaluate_report(report, policy("asset-a"))


def test_incomplete_unified_report_contract_is_rejected():
    report = unified_report(backup_asset("asset-a"))
    del report["evidence_sources"]

    with pytest.raises(ValueError, match="evidence_sources"):
        evaluate_report(report, policy("asset-a"))


def test_duplicate_unified_asset_relationship_is_rejected():
    asset = backup_asset("asset-a")
    report = unified_report(asset, deepcopy(asset))
    report["evidence_sources"][1]["source_id"] = "source-duplicate-asset"

    with pytest.raises(ValueError, match="Duplicate Unified asset_id"):
        evaluate_report(report, policy("asset-a"))


def test_duplicate_unified_source_relationship_is_rejected():
    report = unified_report(backup_asset("asset-a"), backup_asset("asset-b"))
    report["evidence_sources"][1]["source_id"] = report["evidence_sources"][0]["source_id"]

    with pytest.raises(ValueError, match="Duplicate Unified source_id"):
        evaluate_report(report, policy("asset-a"))


def test_cli_writes_valid_separate_output(tmp_path):
    input_path = tmp_path / "input.json"
    policy_path = tmp_path / "policy.json"
    output_path = tmp_path / "output.json"
    write_json(input_path, unified_report(backup_asset("asset-a")))
    write_json(policy_path, policy("asset-a", evaluation_timestamp=None))

    exit_code = main(
        [
            str(input_path),
            "--policy",
            str(policy_path),
            "--output",
            str(output_path),
            "--evaluation-timestamp",
            EVALUATION_TIMESTAMP,
        ]
    )

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["schema_version"] == (
        EVALUATION_SCHEMA_VERSION
    )


def test_cli_evaluates_valid_restore_test_evidence(tmp_path):
    input_path = tmp_path / "input.json"
    policy_path = tmp_path / "policy.json"
    restore_path = tmp_path / "restore.json"
    output_path = tmp_path / "output.json"
    write_json(input_path, unified_report(backup_asset("asset-a")))
    write_json(
        policy_path,
        policy(
            "asset-a",
            evaluation_timestamp=RTO_EVALUATION_TIMESTAMP,
            include_rto=True,
        ),
    )
    write_json(restore_path, restore_test_evidence("valid_pass.json"))

    exit_code = main(
        [
            str(input_path),
            "--policy",
            str(policy_path),
            "--restore-test-evidence",
            str(restore_path),
            "--output",
            str(output_path),
        ]
    )

    output = json.loads(output_path.read_text(encoding="utf-8"))
    rto = output["asset_results"][0]["evaluations"][1]
    assert exit_code == 0
    assert rto["status"] == "PASS"


def test_cli_fails_closed_for_invalid_restore_test_evidence(tmp_path):
    input_path = tmp_path / "input.json"
    policy_path = tmp_path / "policy.json"
    restore_path = tmp_path / "restore.json"
    output_path = tmp_path / "output.json"
    invalid_evidence = restore_test_evidence("valid_pass.json")
    invalid_evidence["restore_tests"][0]["duration_seconds"] = 1
    write_json(input_path, unified_report(backup_asset("asset-a")))
    write_json(policy_path, policy("asset-a", include_rto=True))
    write_json(restore_path, invalid_evidence)

    exit_code = main(
        [
            str(input_path),
            "--policy",
            str(policy_path),
            "--restore-test-evidence",
            str(restore_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code != 0
    assert not output_path.exists()


def test_cli_refuses_restore_test_evidence_path_as_output(tmp_path, capsys):
    input_path = tmp_path / "input.json"
    policy_path = tmp_path / "policy.json"
    restore_path = tmp_path / "restore.json"
    write_json(input_path, unified_report(backup_asset("asset-a")))
    write_json(policy_path, policy("asset-a", include_rto=True))
    write_json(restore_path, restore_test_evidence("valid_pass.json"))

    exit_code = main(
        [
            str(input_path),
            "--policy",
            str(policy_path),
            "--restore-test-evidence",
            str(restore_path),
            "--output",
            str(restore_path),
        ]
    )

    assert exit_code != 0
    assert "Output path must differ" in capsys.readouterr().err
    assert json.loads(restore_path.read_text(encoding="utf-8"))["schema_version"] == (
        "restore-test-evidence/v1"
    )


@pytest.mark.parametrize("same_as", ["input", "policy"])
def test_cli_refuses_input_or_policy_path_as_output(tmp_path, capsys, same_as):
    input_path = tmp_path / "input.json"
    policy_path = tmp_path / "policy.json"
    write_json(input_path, unified_report(backup_asset("asset-a")))
    write_json(policy_path, policy("asset-a"))
    output_path = input_path if same_as == "input" else policy_path

    exit_code = main(
        [
            str(input_path),
            "--policy",
            str(policy_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code != 0
    assert "Output path must differ" in capsys.readouterr().err


def test_cli_refuses_existing_output(tmp_path, capsys):
    input_path = tmp_path / "input.json"
    policy_path = tmp_path / "policy.json"
    output_path = tmp_path / "output.json"
    write_json(input_path, unified_report(backup_asset("asset-a")))
    write_json(policy_path, policy("asset-a"))
    output_path.write_text("existing", encoding="utf-8")

    exit_code = main(
        [
            str(input_path),
            "--policy",
            str(policy_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code != 0
    assert "already exists" in capsys.readouterr().err
    assert output_path.read_text(encoding="utf-8") == "existing"


@pytest.mark.parametrize("invalid_target", ["policy", "report"])
def test_cli_returns_nonzero_for_invalid_json_contract(tmp_path, invalid_target):
    input_path = tmp_path / "input.json"
    policy_path = tmp_path / "policy.json"
    output_path = tmp_path / "output.json"
    report = unified_report(backup_asset("asset-a"))
    input_policy = policy("asset-a")
    if invalid_target == "policy":
        input_policy["rules"][0]["password"] = "blocked"
    else:
        report["report_type"] = "invalid"
    write_json(input_path, report)
    write_json(policy_path, input_policy)

    exit_code = main(
        [
            str(input_path),
            "--policy",
            str(policy_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code != 0
    assert not output_path.exists()


def test_evaluator_has_no_network_or_external_client_imports():
    syntax_tree = ast.parse(EVALUATOR_PATH.read_text(encoding="utf-8"))
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
        {
            "aiohttp",
            "httpx",
            "paramiko",
            "requests",
            "socket",
            "urllib",
        }
    )


def test_evaluator_has_no_external_connection_or_control_hooks():
    source = EVALUATOR_PATH.read_text(encoding="utf-8").lower()

    for prohibited_text in (
        "api_read_only",
        "authentication",
        "certificate",
        "connection",
        "credential",
        "delete",
        "get /jobs",
        "job-control",
        ".now(",
        "retry",
        "secret",
        "session-id",
        "start_job",
        "tls",
        "use_api",
        "veeam",
    ):
        assert prohibited_text not in source
