# Sanitized Veeam Enterprise Manager Fixtures

These minimal, network-free fixtures model Veeam Backup Enterprise Manager
resource patterns without containing real hosts, customer identifiers,
credentials, tokens, or raw production responses.

The shapes are based on the official Enterprise Manager REST API resource
patterns:

* `/backups`: backup entity fields and repository relationships described by
  `GET /query?type=Backup`.
* `/backupSessions`: backup-job execution session entity fields described by
  `GET /backupSessions/{ID}`.
* `/restorePoints`: entity-reference collection patterns described by
  `GET /backups/{ID}/restorePoints`.
* `/query?type=Repository`: query-result, entity, repository, and link patterns
  described by `GET /query?type=Repository`.

All `Href` values are relative fixture references. Backup sessions in these
fixtures are backup-job executions, not authentication or logon sessions.
The documented repository and restore-point fixture patterns intentionally omit
relationships required by `veeam-evidence-report/v1`; the conservative mapping
therefore omits those resources instead of inventing relationships.

Official references:

* https://helpcenter.veeam.com/docs/vbr/em_rest/get_query_backup.html
* https://helpcenter.veeam.com/docs/vbr/em_rest/get_backupsessions_id.html
* https://helpcenter.veeam.com/docs/vbr/em_rest/get_backups_id_restorepoints.html
* https://helpcenter.veeam.com/docs/vbr/em_rest/get_query_repository.html
