from copy import deepcopy

import pytest

from src.tools.veeam_enterprise_manager_collector import ReadOnlyRequest
from src.tools.veeam_enterprise_manager_collector import (
    VeeamEnterpriseManagerReadOnlyCollector,
)
from src.tools.veeam_evidence_contract import validate_veeam_collector_profile
from src.tools.veeam_unified_report_adapter import adapt_veeam_report_to_unified


TIMESTAMP = "2026-06-10T10:00:00+00:00"
ALLOWED_TARGETS = (
    "/backups",
    "/backupSessions",
    "/restorePoints",
    "/query?type=Repository",
)


class FakeTransport:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.requests = []

    def send(self, request: ReadOnlyRequest) -> object:
        self.requests.append(request)
        return deepcopy(self.responses.get(request.target, {}))


def make_collector(responses=None) -> tuple[VeeamEnterpriseManagerReadOnlyCollector, FakeTransport]:
    transport = FakeTransport(responses)
    return VeeamEnterpriseManagerReadOnlyCollector(transport), transport


@pytest.mark.parametrize("target", ALLOWED_TARGETS)
def test_allowlisted_get_target_calls_fake_transport(target):
    collector, transport = make_collector({target: {"result": "sanitized"}})

    assert collector.request("GET", target) == {"result": "sanitized"}
    assert transport.requests == [ReadOnlyRequest(method="GET", target=target)]


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
    ],
)
def test_unknown_or_inexact_get_targets_are_blocked_before_transport(target):
    collector, transport = make_collector()

    with pytest.raises(ValueError, match="Blocked Veeam Enterprise Manager target"):
        collector.request("GET", target)

    assert transport.requests == []


def test_fake_responses_are_normalized_to_api_read_only_v1_report():
    collector, transport = make_collector(
        {
            "/backups": {"backups": [{"backup_id": "backup-1"}]},
            "/backupSessions": {"sessions": [{"session_id": "session-1"}]},
            "/restorePoints": {
                "restore_points": [
                    {
                        "restore_point_id": "restore-point-1",
                        "job_id": "job-relationship-from-response",
                        "created_at": "2026-06-10T09:00:00+00:00",
                    }
                ]
            },
            "/query?type=Repository": {
                "repositories": [
                    {
                        "repository_id": "repository-1",
                        "repository_name": "Sanitized repository",
                        "storage_target_id": "target-relationship-from-response",
                    }
                ]
            },
        }
    )

    report = collector.collect(TIMESTAMP)

    assert validate_veeam_collector_profile(report) == "api_read_only"
    assert report["schema_version"] == "veeam-evidence-report/v1"
    assert report["overall_status"] == "INCOMPLETE"
    assert report["backup_jobs"] == []
    assert report["storage_targets"] == []
    assert report["repositories"][0]["evidence"]["status"] == "UNKNOWN"
    assert report["restore_points"][0]["evidence"]["status"] == "UNKNOWN"
    assert [request.target for request in transport.requests] == list(ALLOWED_TARGETS)


def test_incomplete_fake_resources_are_omitted_without_inventing_relationships():
    collector, _ = make_collector(
        {
            "/restorePoints": {
                "restore_points": [
                    {
                        "restore_point_id": "restore-point-1",
                        "created_at": "2026-06-10T09:00:00+00:00",
                    }
                ]
            },
            "/query?type=Repository": {
                "repositories": [
                    {
                        "repository_id": "repository-1",
                        "repository_name": "Sanitized repository",
                    }
                ]
            },
        }
    )

    report = collector.collect(TIMESTAMP)

    assert report["repositories"] == []
    assert report["restore_points"] == []
    assert report["overall_status"] == "INCOMPLETE"


def test_api_read_only_report_remains_rejected_by_unified_adapter():
    collector, _ = make_collector()
    report = collector.collect(TIMESTAMP)

    with pytest.raises(ValueError, match="accepts mock_only evidence only"):
        adapt_veeam_report_to_unified(report)
