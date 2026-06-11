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


def _completeness_finding(
    resource_type: str,
    resource_id: str | None,
    reason: str,
    message: str,
) -> dict:
    return {
        "resource_type": resource_type,
        "resource_id": resource_id,
        "reason": reason,
        "evidence": {
            "status": "UNKNOWN",
            "reason": reason,
            "message": message,
        },
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


def _safe_resource_id(item: dict, *fields: str) -> str | None:
    for field in fields:
        value = item.get(field)
        if isinstance(value, str) and value:
            return value
    return None


def _links(item: dict) -> list[dict]:
    links = _nested_list(item, "Links", "Link")
    return [link for link in links if isinstance(link, dict)]


def _linked_hrefs(item: dict, relationship: str, link_type: str) -> list[str]:
    return [
        link["Href"]
        for link in _links(item)
        if link.get("Rel") == relationship
        and link.get("Type") == link_type
        and isinstance(link.get("Href"), str)
        and link["Href"]
    ]


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


def _successful_session_times(response: object) -> dict[str, dict[str, str]]:
    sessions = _nested_list(
        response,
        "Entities",
        "BackupJobSessions",
        "BackupJobSession",
    )
    successful_by_job: dict[str, dict[str, list[tuple[datetime, str]]]] = {}
    for session in sessions:
        if not isinstance(session, dict):
            continue
        values = _non_empty_strings(session, "JobUid", "JobName", "EndTime")
        if (
            values is None
            or session.get("Result") != "Success"
            or session.get("State") != "Stopped"
        ):
            continue
        job_id, job_name, end_time = values
        parsed_end_time = _parse_timestamp(end_time)
        if parsed_end_time is None:
            continue
        successful_by_job.setdefault(job_id, {}).setdefault(job_name, []).append(
            (parsed_end_time, end_time)
        )

    return {
        job_id: {
            job_name: max(session_times, key=lambda item: item[0])[1]
            for job_name, session_times in sessions_by_name.items()
        }
        for job_id, sessions_by_name in successful_by_job.items()
    }


def _normalize_backup_jobs(
    backups_response: object,
    sessions_response: object,
) -> tuple[list[dict], dict[str, dict | None], list[dict]]:
    backups = _nested_list(backups_response, "Entities", "Backups", "Backup")
    successful_times = _successful_session_times(sessions_response)
    candidates_by_job: dict[str, list[tuple[dict, dict]]] = {}
    findings = []

    if not backups:
        for backup_reference in _nested_list(
            backups_response,
            "EntityReferences",
            "Ref",
        ):
            if isinstance(backup_reference, dict):
                findings.append(
                    _completeness_finding(
                        "backup_job",
                        _safe_resource_id(backup_reference, "UID"),
                        "MissingBackupJobRelationship",
                        "The backup reference does not expose every relationship "
                        "required to map a backup job.",
                    )
                )

    for backup in backups:
        if not isinstance(backup, dict):
            continue
        resource_id = _safe_resource_id(backup, "UID", "JobUid")
        values = _non_empty_strings(
            backup,
            "JobUid",
            "JobName",
            "Platform",
            "RepositoryUid",
        )
        if values is None:
            findings.append(
                _completeness_finding(
                    "backup_job",
                    resource_id,
                    "MissingBackupJobRelationship",
                    "The backup does not expose every relationship required to map "
                    "a backup job.",
                )
            )
            continue
        job_id, job_name, workload_type, repository_id = values
        last_successful_backup = successful_times.get(job_id, {}).get(job_name)
        if last_successful_backup is None:
            findings.append(
                _completeness_finding(
                    "backup_job",
                    job_id,
                    "NoDeterministicSuccessfulSession",
                    "No stopped, successful, UTC-timestamped session is explicitly "
                    "linked to the backup job.",
                )
            )
            continue

        candidates_by_job.setdefault(job_id, []).append(
            (
                {
                    "job_id": job_id,
                    "job_name": job_name,
                    "workload_type": workload_type,
                    "repository_id": repository_id,
                    "last_successful_backup": last_successful_backup,
                    "evidence": _unknown_evidence("backup job"),
                },
                backup,
            )
        )

    backup_jobs = []
    backups_by_href = {}
    for job_id, candidates in candidates_by_job.items():
        if len(candidates) != 1:
            findings.append(
                _completeness_finding(
                    "backup_job",
                    job_id,
                    "AmbiguousBackupJobRelationship",
                    "Multiple backups expose the same backup-job relationship.",
                )
            )
            continue

        backup_job, backup = candidates[0]
        backup_jobs.append(backup_job)
        backup_href = backup.get("Href")
        if isinstance(backup_href, str) and backup_href:
            if backup_href in backups_by_href:
                backups_by_href[backup_href] = None
            else:
                backups_by_href[backup_href] = backup_job

    return backup_jobs, backups_by_href, findings


def _normalize_repositories(
    response: object,
    backup_jobs: list[dict],
) -> tuple[list[dict], list[dict]]:
    repositories_response = _nested_list(
        response,
        "QueryResult",
        "Entities",
        "Repositories",
        "Repository",
    )

    repositories = []
    findings = []
    linked_repository_ids = {job["repository_id"] for job in backup_jobs}
    candidates_by_id: dict[str, list[dict]] = {}
    for item in repositories_response:
        if not isinstance(item, dict):
            continue

        repository_id = _safe_resource_id(item, "UID", "repository_id")
        if repository_id is None:
            findings.append(
                _completeness_finding(
                    "repository",
                    None,
                    "MissingRepositoryIdentifier",
                    "The repository cannot be mapped without a safe identifier.",
                )
            )
            continue
        candidates_by_id.setdefault(repository_id, []).append(item)

    for repository_id, candidates in candidates_by_id.items():
        if len(candidates) != 1:
            findings.append(
                _completeness_finding(
                    "repository",
                    repository_id,
                    "AmbiguousRepositoryIdentity",
                    "Multiple repository observations expose the same identifier.",
                )
            )
            continue

        item = candidates[0]
        if repository_id not in linked_repository_ids:
            findings.append(
                _completeness_finding(
                    "repository",
                    repository_id,
                    "UnlinkedRepository",
                    "The repository is not explicitly linked to a mapped backup job.",
                )
            )
            continue

        values = _non_empty_strings(
            item,
            "UID",
            "Name",
            "StorageTargetUid",
        )
        if values is None:
            findings.append(
                _completeness_finding(
                    "repository",
                    repository_id,
                    "MissingStorageTargetRelationship",
                    "The repository has no explicit storage-target relationship "
                    "required by the evidence contract.",
                )
            )
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

    return repositories, findings


def _normalize_restore_points(
    response: object,
    backup_jobs: list[dict],
    backups_by_href: dict[str, dict | None],
) -> tuple[list[dict], list[dict]]:
    restore_points_response = _nested_list(response, "EntityReferences", "Ref")

    restore_points = []
    findings = []
    mapped_job_ids = {job["job_id"] for job in backup_jobs}
    for item in restore_points_response:
        if not isinstance(item, dict):
            continue

        restore_point_id = _safe_resource_id(item, "UID", "restore_point_id")
        if restore_point_id is None:
            findings.append(
                _completeness_finding(
                    "restore_point",
                    None,
                    "MissingRestorePointIdentifier",
                    "The restore point cannot be mapped without a safe identifier.",
                )
            )
            continue

        backup_hrefs = _linked_hrefs(item, "Up", "BackupReference")
        linked_jobs = {
            backups_by_href[href]["job_id"]
            for href in backup_hrefs
            if href in backups_by_href and backups_by_href[href] is not None
        }
        if len(backup_hrefs) != 1 or len(linked_jobs) != 1:
            reason = (
                "AmbiguousRestorePointRelationship"
                if len(backup_hrefs) > 1
                or len(linked_jobs) > 1
                or any(
                    href in backups_by_href and backups_by_href[href] is None
                    for href in backup_hrefs
                )
                else "UnlinkedRestorePoint"
            )
            findings.append(
                _completeness_finding(
                    "restore_point",
                    restore_point_id,
                    reason,
                    "The restore point is not explicitly and uniquely linked to "
                    "a mapped backup job.",
                )
            )
            continue
        job_id = next(iter(linked_jobs))
        created_at = item.get("CreationTimeUTC")
        if not isinstance(created_at, str) or not created_at:
            findings.append(
                _completeness_finding(
                    "restore_point",
                    restore_point_id,
                    "MissingRestorePointTimestamp",
                    "The restore-point reference does not expose the UTC creation "
                    "timestamp required by the evidence contract.",
                )
            )
            continue

        if job_id not in mapped_job_ids:
            findings.append(
                _completeness_finding(
                    "restore_point",
                    restore_point_id,
                    "UnlinkedRestorePoint",
                    "The restore point is not linked to a mapped backup job.",
                )
            )
            continue
        if _parse_timestamp(created_at) is None:
            findings.append(
                _completeness_finding(
                    "restore_point",
                    restore_point_id,
                    "InvalidRestorePointTimestamp",
                    "The restore point does not expose a valid UTC creation timestamp.",
                )
            )
            continue

        restore_points.append(
            {
                "restore_point_id": restore_point_id,
                "job_id": job_id,
                "created_at": created_at,
                "evidence": _unknown_evidence("restore point"),
            }
        )

    return restore_points, findings


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
        backup_jobs, backups_by_href, backup_findings = _normalize_backup_jobs(
            backups_response,
            sessions_response,
        )
        repositories, repository_findings = _normalize_repositories(
            repositories_response,
            backup_jobs,
        )
        restore_points, restore_point_findings = _normalize_restore_points(
            restore_points_response,
            backup_jobs,
            backups_by_href,
        )
        completeness_findings = sorted(
            backup_findings + repository_findings + restore_point_findings,
            key=lambda finding: (
                finding["resource_type"],
                finding["resource_id"] or "",
                finding["reason"],
            ),
        )

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
            "backup_jobs": backup_jobs,
            "repositories": repositories,
            "restore_points": restore_points,
            "storage_targets": [],
            "completeness_findings": completeness_findings,
        }
        validate_veeam_collector_profile(report)
        return report
