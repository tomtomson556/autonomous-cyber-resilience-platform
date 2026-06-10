import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.tools.veeam_enterprise_manager_collector import ALLOWED_REQUEST_TARGETS
from src.tools.veeam_enterprise_manager_collector import ReadOnlyRequest
from src.tools.veeam_enterprise_manager_collector import (
    VeeamEnterpriseManagerReadOnlyCollector,
)
from src.tools.veeam_evidence_contract import validate_veeam_collector_profile
from src.tools.veeam_unified_report_adapter import adapt_veeam_report_to_unified


TIMESTAMP = "2026-06-10T10:00:00+00:00"
FIXTURE_DIRECTORY = Path(__file__).resolve().parent / "fixtures" / "veeam"
ALLOWED_TARGETS = (
    "/backups",
    "/backupSessions",
    "/restorePoints",
    "/query?type=Repository",
)


def load_fixture(name: str) -> dict:
    with (FIXTURE_DIRECTORY / name).open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def contract_shaped_responses() -> dict:
    return {
        "/backups": load_fixture("backups.json"),
        "/backupSessions": load_fixture("backup_sessions.json"),
        "/restorePoints": load_fixture("restore_points.json"),
        "/query?type=Repository": load_fixture("repositories.json"),
    }


class FakeTransport:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.requests = []

    def send(self, request: ReadOnlyRequest) -> object:
        self.requests.append(request)
        return deepcopy(self.responses.get(request.target, {}))


def make_collector(
    responses=None,
) -> tuple[VeeamEnterpriseManagerReadOnlyCollector, FakeTransport]:
    transport = FakeTransport(responses)
    return VeeamEnterpriseManagerReadOnlyCollector(transport), transport


@pytest.mark.parametrize("target", ALLOWED_TARGETS)
def test_allowlisted_get_target_calls_fake_transport(target):
    collector, transport = make_collector({target: {"result": "sanitized"}})

    assert collector.request("GET", target) == {"result": "sanitized"}
    assert transport.requests == [ReadOnlyRequest(method="GET", target=target)]


def test_internal_get_allowlist_is_exact_and_unchanged():
    assert ALLOWED_REQUEST_TARGETS == frozenset(ALLOWED_TARGETS)


@pytest.mark.parametrize(
    "method",
    ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "get"],
)
def test_non_get_methods_are_blocked_before_transport(method):
    collector, transport = make_collector()

    with pytest.raises(ValueError, match="Blocked Veeam Enterprise Manager method"):
        collector.request(method, "/backups")

    assert transport.requests == []


@pytest.mark.parametrize(
    "target",
    [
        "/jobs",
        "/query",
        "/query?type=Job",
        "/query?type=Repository&foo=bar",
        "/query?foo=bar&type=Repository",
        "/backups?foo=bar",
        "/restorePoints/restore-point-1",
        "/logonSessions",
        "/sessionMngr/",
    ],
)
def test_unknown_or_inexact_get_targets_are_blocked_before_transport(target):
    collector, transport = make_collector()

    with pytest.raises(ValueError, match="Blocked Veeam Enterprise Manager target"):
        collector.request("GET", target)

    assert transport.requests == []


def test_auth_session_manager_post_is_blocked_before_transport():
    collector, transport = make_collector()

    with pytest.raises(ValueError, match="Blocked Veeam Enterprise Manager method"):
        collector.request("POST", "/sessionMngr/")

    assert transport.requests == []


def test_contract_shaped_fixtures_are_normalized_to_api_read_only_v1_report():
    collector, transport = make_collector(contract_shaped_responses())

    report = collector.collect(TIMESTAMP)

    assert validate_veeam_collector_profile(report) == "api_read_only"
    assert report["schema_version"] == "veeam-evidence-report/v1"
    assert report["overall_status"] == "INCOMPLETE"
    assert report["backup_jobs"] == [
        {
            "job_id": "urn:veeam:Job:job-fixture-001",
            "job_name": "Sanitized Backup Job",
            "workload_type": "VMware",
            "repository_id": "urn:veeam:Repository:repository-fixture-001",
            "last_successful_backup": "2026-06-10T09:00:00+00:00",
            "evidence": {
                "status": "UNKNOWN",
                "reason": "ReadOnlyObservationOnly",
                "message": (
                    "The read-only backup job observation does not prove a "
                    "resilience condition."
                ),
            },
        }
    ]
    assert report["storage_targets"] == []
    assert report["repositories"] == []
    assert report["restore_points"] == []
    assert [request.target for request in transport.requests] == list(ALLOWED_TARGETS)


@pytest.mark.parametrize("missing_field", ["JobUid", "JobName", "Platform", "RepositoryUid"])
def test_incomplete_backup_relationships_are_omitted(missing_field):
    responses = contract_shaped_responses()
    del responses["/backups"]["Entities"]["Backups"]["Backup"][0][missing_field]
    collector, _ = make_collector(responses)

    report = collector.collect(TIMESTAMP)

    assert report["backup_jobs"] == []
    assert report["overall_status"] == "INCOMPLETE"


def test_ambiguous_duplicate_job_relationship_is_omitted():
    responses = contract_shaped_responses()
    backup = responses["/backups"]["Entities"]["Backups"]["Backup"][0]
    responses["/backups"]["Entities"]["Backups"]["Backup"].append(deepcopy(backup))
    collector, _ = make_collector(responses)

    report = collector.collect(TIMESTAMP)

    assert report["backup_jobs"] == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("Result", "Failed"),
        ("Result", "Warning"),
        ("Result", None),
        ("State", "Working"),
        ("EndTime", "not-a-timestamp"),
        ("EndTime", "2026-06-10T09:00:00"),
    ],
)
def test_ineligible_session_does_not_create_last_success(
    field,
    value,
):
    responses = contract_shaped_responses()
    session = responses["/backupSessions"]["Entities"]["BackupJobSessions"][
        "BackupJobSession"
    ][0]
    if value is None:
        del session[field]
    else:
        session[field] = value
    collector, _ = make_collector(responses)

    report = collector.collect(TIMESTAMP)

    assert report["backup_jobs"] == []


def test_non_utc_successful_session_does_not_create_last_success():
    responses = contract_shaped_responses()
    session = responses["/backupSessions"]["Entities"]["BackupJobSessions"][
        "BackupJobSession"
    ][0]
    session["EndTime"] = "2026-06-10T09:00:00+02:00"
    collector, _ = make_collector(responses)

    report = collector.collect(TIMESTAMP)

    assert report["backup_jobs"] == []


def test_unlinked_successful_session_does_not_create_last_success():
    responses = contract_shaped_responses()
    session = responses["/backupSessions"]["Entities"]["BackupJobSessions"][
        "BackupJobSession"
    ][0]
    session["JobUid"] = "urn:veeam:Job:unlinked-fixture-job"
    collector, _ = make_collector(responses)

    report = collector.collect(TIMESTAMP)

    assert report["backup_jobs"] == []


def test_documented_incomplete_resource_relationships_are_not_invented():
    collector, _ = make_collector(contract_shaped_responses())

    report = collector.collect(TIMESTAMP)

    assert report["repositories"] == []
    assert report["restore_points"] == []
    assert report["overall_status"] == "INCOMPLETE"


def test_normalized_legacy_fake_resources_remain_supported():
    collector, _ = make_collector(
        {
            "/restorePoints": {
                "restore_points": [
                    {
                        "restore_point_id": "restore-point-1",
                        "job_id": "job-1",
                        "created_at": "2026-06-10T09:00:00+00:00",
                    }
                ]
            },
            "/query?type=Repository": {
                "repositories": [
                    {
                        "repository_id": "repository-1",
                        "repository_name": "Sanitized repository",
                        "storage_target_id": "storage-target-1",
                    }
                ]
            },
        }
    )

    report = collector.collect(TIMESTAMP)

    assert report["repositories"][0]["repository_id"] == "repository-1"
    assert report["restore_points"][0]["restore_point_id"] == "restore-point-1"


def test_api_read_only_report_remains_rejected_by_unified_adapter():
    collector, _ = make_collector()
    report = collector.collect(TIMESTAMP)

    with pytest.raises(ValueError, match="accepts mock_only evidence only"):
        adapt_veeam_report_to_unified(report)
