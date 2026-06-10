from dataclasses import dataclass
from datetime import datetime
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
# This is an internal, network-free collector contract. Endpoint changes require
# a separate review against official Veeam Enterprise Manager documentation.


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


def _nested_list(response: object, *keys: str) -> list:
    value = response
    for key in keys:
        if not isinstance(value, dict):
            return []
        value = value.get(key)
    return value if isinstance(value, list) else []


def _non_empty_strings(item: dict, *fields: str) -> tuple[str, ...] | None:
    values = tuple(item.get(field) for field in fields)
    if not all(isinstance(value, str) and value for value in values):
        return None
    return values


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not (
        value.endswith("Z") or value.endswith("+00:00")
    ):
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return timestamp


def _successful_session_times(response: object) -> dict[str, str]:
    sessions = _nested_list(
        response,
        "Entities",
        "BackupJobSessions",
        "BackupJobSession",
    )
    successful_by_job: dict[str, list[tuple[datetime, str]]] = {}
    for session in sessions:
        if not isinstance(session, dict):
            continue
        values = _non_empty_strings(session, "JobUid", "EndTime")
        if (
            values is None
            or session.get("Result") != "Success"
            or session.get("State") != "Stopped"
        ):
            continue
        job_id, end_time = values
        parsed_end_time = _parse_timestamp(end_time)
        if parsed_end_time is None:
            continue
        successful_by_job.setdefault(job_id, []).append((parsed_end_time, end_time))

    return {
        job_id: max(session_times, key=lambda item: item[0])[1]
        for job_id, session_times in successful_by_job.items()
    }


def _normalize_backup_jobs(backups_response: object, sessions_response: object) -> list[dict]:
    backups = _nested_list(backups_response, "Entities", "Backups", "Backup")
    successful_times = _successful_session_times(sessions_response)
    candidates_by_job: dict[str, list[dict]] = {}

    for backup in backups:
        if not isinstance(backup, dict):
            continue
        values = _non_empty_strings(
            backup,
            "JobUid",
            "JobName",
            "Platform",
            "RepositoryUid",
        )
        if values is None:
            continue
        job_id, job_name, workload_type, repository_id = values
        last_successful_backup = successful_times.get(job_id)
        if last_successful_backup is None:
            continue

        candidates_by_job.setdefault(job_id, []).append(
            {
                "job_id": job_id,
                "job_name": job_name,
                "workload_type": workload_type,
                "repository_id": repository_id,
                "last_successful_backup": last_successful_backup,
                "evidence": _unknown_evidence("backup job"),
            }
        )

    return [
        candidates[0]
        for candidates in candidates_by_job.values()
        if len(candidates) == 1
    ]


def _normalize_repositories(response: object) -> list[dict]:
    repositories_response = _nested_list(
        response,
        "QueryResult",
        "Entities",
        "Repositories",
        "Repository",
    )
    if not repositories_response and isinstance(response, dict):
        repositories_response = response.get("repositories", [])
    if not isinstance(repositories_response, list):
        return []

    repositories = []
    for item in repositories_response:
        if not isinstance(item, dict):
            continue

        values = _non_empty_strings(
            item,
            "UID",
            "Name",
            "StorageTargetUid",
        )
        if values is None:
            values = _non_empty_strings(
                item,
                "repository_id",
                "repository_name",
                "storage_target_id",
            )
            if values is None:
                continue
        repository_id, repository_name, storage_target_id = values

        repositories.append(
            {
                "repository_id": repository_id,
                "repository_name": repository_name,
                "storage_target_id": storage_target_id,
                "evidence": _unknown_evidence("repository"),
            }
        )

    return repositories


def _normalize_restore_points(response: object) -> list[dict]:
    restore_points_response = _nested_list(response, "EntityReferences", "Ref")
    if not restore_points_response and isinstance(response, dict):
        restore_points_response = response.get("restore_points", [])
    if not isinstance(restore_points_response, list):
        return []

    restore_points = []
    for item in restore_points_response:
        if not isinstance(item, dict):
            continue

        values = _non_empty_strings(
            item,
            "UID",
            "JobUid",
            "CreationTimeUTC",
        )
        if values is None:
            values = _non_empty_strings(
                item,
                "restore_point_id",
                "job_id",
                "created_at",
            )
            if values is None:
                continue
        restore_point_id, job_id, created_at = values

        restore_points.append(
            {
                "restore_point_id": restore_point_id,
                "job_id": job_id,
                "created_at": created_at,
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

        backups_response = self.request("GET", "/backups")
        sessions_response = self.request("GET", "/backupSessions")
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
            "backup_jobs": _normalize_backup_jobs(
                backups_response,
                sessions_response,
            ),
            "repositories": _normalize_repositories(repositories_response),
            "restore_points": _normalize_restore_points(restore_points_response),
            "storage_targets": [],
        }
        validate_veeam_collector_profile(report)
        return report
