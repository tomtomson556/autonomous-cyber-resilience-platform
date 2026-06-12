import json
from copy import deepcopy

import pytest

from src.tools.unified_report_composer import compose_unified_reports, main


def unified_report(
    suffix: str,
    *,
    timestamp: str = "2026-06-12T10:00:00+00:00",
    overall_status: str = "HEALTHY",
    finding_status: str | None = None,
) -> dict:
    findings = []
    if finding_status is not None:
        findings.append(
            {
                "finding_id": f"finding-{suffix}",
                "asset_id": f"asset-{suffix}",
                "category": "test_evidence",
                "status": finding_status,
                "reason": f"{finding_status.title()}Evidence",
                "message": f"The test evidence is {finding_status.lower()}.",
                "confirmed_vulnerability": finding_status == "FAIL",
            }
        )

    return {
        "schema_version": "1.0.0",
        "timestamp": timestamp,
        "platform": "autonomous-cyber-resilience-platform",
        "report_type": "unified_resilience_report",
        "data_classification": "MOCK_EXAMPLE_ONLY",
        "overall_resilience_status": overall_status,
        "evidence_sources": [
            {
                "source_id": f"source-{suffix}",
                "source_type": "test",
                "collected_at": timestamp,
                "status": "PASS",
                "reference": f"mock://source-{suffix}",
            }
        ],
        "assets": [
            {
                "asset_id": f"asset-{suffix}",
                "source_type": "test",
                "backup_system": None,
                "risk_score": None,
                "recommended_action": None,
            }
        ],
        "findings": findings,
        "recommended_actions": [],
    }


def write_report(path, report: dict) -> None:
    path.write_text(json.dumps(report), encoding="utf-8")


def test_composes_two_reports_without_modifying_inputs():
    first = unified_report("b", timestamp="2026-06-12T10:00:00+00:00")
    second = unified_report("a", timestamp="2026-06-12T11:00:00+00:00")
    originals = deepcopy([first, second])

    result = compose_unified_reports([first, second], ["input-b", "input-a"])

    assert [source["source_id"] for source in result["evidence_sources"]] == [
        "source-a",
        "source-b",
    ]
    assert [asset["asset_id"] for asset in result["assets"]] == [
        "asset-a",
        "asset-b",
    ]
    assert result["timestamp"] == second["timestamp"]
    assert [first, second] == originals


def test_result_is_independent_of_input_order():
    first = unified_report("a")
    second = unified_report("b")

    forward = compose_unified_reports([first, second], ["input-a", "input-b"])
    reverse = compose_unified_reports([second, first], ["input-b", "input-a"])

    assert forward == reverse


def test_equal_timestamp_instants_are_independent_of_input_order():
    first = unified_report("a", timestamp="2026-06-12T10:00:00Z")
    second = unified_report("b", timestamp="2026-06-12T10:00:00+00:00")

    forward = compose_unified_reports([first, second], ["input-a", "input-b"])
    reverse = compose_unified_reports([second, first], ["input-b", "input-a"])

    assert forward == reverse


@pytest.mark.parametrize(
    ("collection_name", "id_field"),
    [
        ("evidence_sources", "source_id"),
        ("assets", "asset_id"),
        ("findings", "finding_id"),
    ],
)
def test_duplicate_ids_are_rejected(collection_name, id_field):
    first = unified_report("a", finding_status="UNKNOWN")
    second = unified_report("b", finding_status="UNKNOWN")
    second[collection_name][0][id_field] = first[collection_name][0][id_field]

    with pytest.raises(ValueError, match=f"Duplicate {id_field}"):
        compose_unified_reports([first, second])


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("schema_version", "2.0.0", "Unsupported Unified report schema_version"),
        ("report_type", "source_report", "Unified report_type must be"),
        ("overall_resilience_status", "UNKNOWN", "overall_resilience_status is invalid"),
    ],
)
def test_incompatible_contract_values_are_rejected(field_name, value, message):
    invalid = unified_report("a")
    invalid[field_name] = value

    with pytest.raises(ValueError, match=message):
        compose_unified_reports([invalid, unified_report("b")])


def test_missing_schema_version_is_rejected():
    invalid = unified_report("a")
    del invalid["schema_version"]

    with pytest.raises(ValueError, match="schema_version is required"):
        compose_unified_reports([invalid, unified_report("b")])


@pytest.mark.parametrize(
    "timestamp",
    ["not-a-timestamp", "2026-06-12T10:00:00"],
)
def test_invalid_or_offset_free_timestamp_is_rejected(timestamp):
    invalid = unified_report("a", timestamp=timestamp)

    with pytest.raises(ValueError, match="timestamp"):
        compose_unified_reports([invalid, unified_report("b")])


def test_missing_required_collection_is_rejected():
    invalid = unified_report("a")
    del invalid["findings"]

    with pytest.raises(ValueError, match="'findings' must be a list"):
        compose_unified_reports([invalid, unified_report("b")])


@pytest.mark.parametrize(
    ("first_status", "second_status", "expected"),
    [
        ("HEALTHY", "INCOMPLETE", "INCOMPLETE"),
        ("HEALTHY", "AT_RISK", "AT_RISK"),
        ("INCOMPLETE", "AT_RISK", "AT_RISK"),
        ("AT_RISK", "CRITICAL", "CRITICAL"),
    ],
)
def test_mixed_input_statuses_are_combined_conservatively(
    first_status,
    second_status,
    expected,
):
    result = compose_unified_reports(
        [
            unified_report("a", overall_status=first_status),
            unified_report("b", overall_status=second_status),
        ]
    )

    assert result["overall_resilience_status"] == expected


def test_incomplete_input_without_findings_remains_incomplete():
    result = compose_unified_reports(
        [
            unified_report("a", overall_status="INCOMPLETE"),
            unified_report("b"),
        ]
    )

    assert result["findings"] == []
    assert result["overall_resilience_status"] == "INCOMPLETE"


def test_unknown_finding_is_preserved_and_never_confirmed():
    unknown_report = unified_report("a", finding_status="UNKNOWN")

    result = compose_unified_reports([unknown_report, unified_report("b")])

    assert result["findings"][0] == unknown_report["findings"][0]
    assert result["findings"][0]["confirmed_vulnerability"] is False
    assert result["overall_resilience_status"] == "INCOMPLETE"


def test_confirmed_unknown_finding_is_rejected():
    invalid = unified_report("a", finding_status="UNKNOWN")
    invalid["findings"][0]["confirmed_vulnerability"] = True

    with pytest.raises(ValueError, match="cannot confirm UNKNOWN evidence"):
        compose_unified_reports([invalid, unified_report("b")])


def test_provenance_contains_stable_input_details():
    first = unified_report("a", overall_status="INCOMPLETE")
    second = unified_report("b")

    result = compose_unified_reports([first, second], ["input-a", "input-b"])

    assert result["provenance"] == {
        "composer": "unified_report_composer",
        "input_reports": [
            {
                "input_identifier": "input-a",
                "timestamp": first["timestamp"],
                "schema_version": "1.0.0",
                "report_type": "unified_resilience_report",
                "evidence_source_ids": ["source-a"],
                "overall_resilience_status": "INCOMPLETE",
            },
            {
                "input_identifier": "input-b",
                "timestamp": second["timestamp"],
                "schema_version": "1.0.0",
                "report_type": "unified_resilience_report",
                "evidence_source_ids": ["source-b"],
                "overall_resilience_status": "HEALTHY",
            },
        ],
    }


def test_data_classification_conflict_is_rejected():
    second = unified_report("b")
    second["data_classification"] = "LOCAL_ADAPTER_OUTPUT"

    with pytest.raises(ValueError, match="same data_classification"):
        compose_unified_reports([unified_report("a"), second])


def test_collections_and_actions_are_sorted_deterministically():
    first = unified_report("b", finding_status="UNKNOWN")
    first["recommended_actions"] = [
        {"summary": "Zulu"},
        {"action_id": "action-z", "summary": "Alpha"},
    ]
    second = unified_report("a", finding_status="FAIL")
    second["recommended_actions"] = [{"action_id": "action-a", "summary": "Beta"}]

    result = compose_unified_reports([first, second], ["input-b", "input-a"])

    assert [item["source_id"] for item in result["evidence_sources"]] == [
        "source-a",
        "source-b",
    ]
    assert [item["asset_id"] for item in result["assets"]] == ["asset-a", "asset-b"]
    assert [item["finding_id"] for item in result["findings"]] == [
        "finding-a",
        "finding-b",
    ]
    assert result["recommended_actions"] == [
        {"action_id": "action-a", "summary": "Beta"},
        {"action_id": "action-z", "summary": "Alpha"},
        {"summary": "Zulu"},
    ]


def test_duplicate_action_id_is_rejected():
    first = unified_report("a")
    first["recommended_actions"] = [{"action_id": "action-duplicate"}]
    second = unified_report("b")
    second["recommended_actions"] = [{"action_id": "action-duplicate"}]

    with pytest.raises(ValueError, match="Duplicate action_id"):
        compose_unified_reports([first, second])


def test_cli_writes_deterministic_json(tmp_path):
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    output_path = tmp_path / "composed.json"
    write_report(first_path, unified_report("a"))
    write_report(second_path, unified_report("b"))

    exit_code = main(
        [str(first_path), str(second_path), "--output", str(output_path)]
    )

    assert exit_code == 0
    output = output_path.read_text(encoding="utf-8")
    assert output.endswith("\n")
    assert json.loads(output)["provenance"]["composer"] == "unified_report_composer"


@pytest.mark.parametrize("invalid_input", ["invalid_json", "missing_file"])
def test_cli_rejects_invalid_input_files(tmp_path, capsys, invalid_input):
    valid_path = tmp_path / "valid.json"
    invalid_path = tmp_path / "invalid.json"
    output_path = tmp_path / "output.json"
    write_report(valid_path, unified_report("a"))
    if invalid_input == "invalid_json":
        invalid_path.write_text("{", encoding="utf-8")

    exit_code = main(
        [str(valid_path), str(invalid_path), "--output", str(output_path)]
    )

    assert exit_code != 0
    assert "Unified report composition failed:" in capsys.readouterr().err
    assert not output_path.exists()


def test_cli_rejects_fewer_than_two_inputs(tmp_path, capsys):
    input_path = tmp_path / "input.json"
    write_report(input_path, unified_report("a"))

    exit_code = main([str(input_path), "--output", str(tmp_path / "output.json")])

    assert exit_code != 0
    assert "At least two input files are required" in capsys.readouterr().err


def test_cli_rejects_output_path_identical_to_input(tmp_path, capsys):
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    write_report(first_path, unified_report("a"))
    write_report(second_path, unified_report("b"))

    exit_code = main(
        [str(first_path), str(second_path), "--output", str(first_path)]
    )

    assert exit_code != 0
    assert "must not be identical" in capsys.readouterr().err


def test_cli_does_not_overwrite_existing_output(tmp_path, capsys):
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    output_path = tmp_path / "output.json"
    write_report(first_path, unified_report("a"))
    write_report(second_path, unified_report("b"))
    output_path.write_text("existing", encoding="utf-8")

    exit_code = main(
        [str(first_path), str(second_path), "--output", str(output_path)]
    )

    assert exit_code != 0
    assert "already exists" in capsys.readouterr().err
    assert output_path.read_text(encoding="utf-8") == "existing"
