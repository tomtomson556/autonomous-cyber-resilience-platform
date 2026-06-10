from dataclasses import dataclass
from typing import Protocol

from src.tools.veeam_evidence_contract import API_READ_ONLY_COLLECTOR_NAME
from src.tools.veeam_evidence_contract import API_READ_ONLY_DATA_CLASSIFICATION
from src.tools.veeam_evidence_contract import validate_veeam_collector_profile


VEEAM_SCHEMA_VERSION = "veeam-evidence-report/v1"

ALLOWED_REQUEST_TARGETS = frozenset(
    {
        "/backups",
        "/backupSessions",
        "/restorePoints",
        "/query?type=Repository",
    }
)


@dataclass(frozen=True)
class ReadOnlyRequest:
    method: str
    target: str


class ReadOnlyTransport(Protocol):
    def send(self, request: ReadOnlyRequest) -> object:
        """Return a sanitized fake response for an allowed read-only request."""


def validate_read_only_request(request: ReadOnlyRequest) -> None:
    if request.method != "GET":
        raise ValueError(f"Blocked Veeam Enterprise Manager method: {request.method}")

    if request.target not in ALLOWED_REQUEST_TARGETS:
        raise ValueError(f"Blocked Veeam Enterprise Manager target: {request.target}")


def _unknown_evidence(resource_type: str) -> dict:
    return {
        "status": "UNKNOWN",
        "reason": "ReadOnlyObservationOnly",
        "message": (
            f"The read-only {resource_type} observation does not prove a "
            "resilience condition."
        ),
    }


def _normalize_repositories(response: object) -> list[dict]:
    if not isinstance(response, dict) or not isinstance(
        response.get("repositories"), list
    ):
        return []

    repositories = []
    for item in response["repositories"]:
        if not isinstance(item, dict):
            continue

        required_values = (
            item.get("repository_id"),
            item.get("repository_name"),
            item.get("storage_target_id"),
        )
        if not all(isinstance(value, str) and value for value in required_values):
            continue

        repositories.append(
            {
                "repository_id": item["repository_id"],
                "repository_name": item["repository_name"],
                "storage_target_id": item["storage_target_id"],
                "evidence": _unknown_evidence("repository"),
            }
        )

    return repositories


def _normalize_restore_points(response: object) -> list[dict]:
    if not isinstance(response, dict) or not isinstance(
        response.get("restore_points"), list
    ):
        return []

    restore_points = []
    for item in response["restore_points"]:
        if not isinstance(item, dict):
            continue

        required_values = (
            item.get("restore_point_id"),
            item.get("job_id"),
            item.get("created_at"),
        )
        if not all(isinstance(value, str) and value for value in required_values):
            continue

        restore_points.append(
            {
                "restore_point_id": item["restore_point_id"],
                "job_id": item["job_id"],
                "created_at": item["created_at"],
                "evidence": _unknown_evidence("restore point"),
            }
        )

    return restore_points


class VeeamEnterpriseManagerReadOnlyCollector:
    """Network-free groundwork that emits sanitized api_read_only evidence."""

    def __init__(self, transport: ReadOnlyTransport):
        self._transport = transport

    def request(self, method: str, target: str) -> object:
        request = ReadOnlyRequest(method=method, target=target)
        validate_read_only_request(request)
        return self._transport.send(request)

    def collect(self, timestamp: str) -> dict:
        if not isinstance(timestamp, str) or not timestamp:
            raise ValueError("Collection timestamp must be a non-empty string.")

        self.request("GET", "/backups")
        self.request("GET", "/backupSessions")
        restore_points_response = self.request("GET", "/restorePoints")
        repositories_response = self.request("GET", "/query?type=Repository")

        report = {
            "schema_version": VEEAM_SCHEMA_VERSION,
            "timestamp": timestamp,
            "report_type": "veeam_evidence_report",
            "data_classification": API_READ_ONLY_DATA_CLASSIFICATION,
            "collector": {
                "name": API_READ_ONLY_COLLECTOR_NAME,
                "mode": "api_read_only",
            },
            "overall_status": "INCOMPLETE",
            "backup_jobs": [],
            "repositories": _normalize_repositories(repositories_response),
            "restore_points": _normalize_restore_points(restore_points_response),
            "storage_targets": [],
        }
        validate_veeam_collector_profile(report)
        return report
