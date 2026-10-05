# PostgreSQL backup and restore runbook

This runbook describes manual PostgreSQL backups for a deployment operator. QueueSense does not currently ship an automated backup scheduler or claim a completed restore drill. Use a separate, access-restricted destination; never commit dumps or credentials to the repository.

## Create a backup

Provide `DATABASE_URL` through the deployment secret manager or shell (not as a command-line argument). Choose a private destination with sufficient free space:

```sh
umask 077
pg_dump --format=custom --no-owner --no-acl --file="queuesense-$(date -u +%Y%m%dT%H%M%SZ).dump" "$DATABASE_URL"
```

Encrypt the resulting file at rest using the organization's approved key management, transfer it over an authenticated encrypted channel, and restrict access to designated operators. Retain backups according to the deployment's approved retention policy. Store encryption keys separately from backup files.

## Restore rehearsal

Restore into a newly created, isolated PostgreSQL database. Do not restore over a live database as a rehearsal. Supply source and destination connection strings via protected environment variables and run:

```sh
pg_restore --no-owner --no-acl --dbname="$RESTORE_DATABASE_URL" "$BACKUP_FILE"
```

Run the application's migration/integrity checks against the restored database, compare expected schema versions and representative row counts, and verify a read-only application startup. Record the backup timestamp, restore duration, checks performed, and any data loss window. Remove the rehearsal database and temporary dump securely after recording the outcome.

Before production use, operators must decide backup frequency, recovery point/time objectives, retention, encryption/key rotation, monitoring, and ownership. A successful dump command alone does not prove recoverability; schedule and record restore rehearsals.
