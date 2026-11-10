# Sources: SQL Server, PostgreSQL, MySQL, Oracle

Only what the source's pages ([SKILL.md](../SKILL.md#modes-per-source)) don't make obvious. Read the source's troubleshoot and limits pages first.

## Where names go

| Source | `connection_type` | `source_catalog` | `source_schema` |
|---|---|---|---|
| SQL Server | `SQLSERVER` | database | schema (`dbo`) |
| PostgreSQL | `POSTGRESQL` | database | schema (`public`) |
| MySQL | `MYSQL` | omit | database |
| Oracle | `ORACLE` | the service the Oracle pipeline page names for the mode | owner, uppercase |

Same-name tables: SQL Server "can't ingest two or more tables with the same name in the same pipeline, even if they come from different source schemas" (two pipelines); MySQL can't ingest them "to the same destination schema" (a destination schema each).

**TLS:** when CDC fails with `INGESTION_GATEWAY_TLS_VALIDATION_FAILURE` (or queries fail with `FAILED_JDBC.CONNECTION`), the server's certificate isn't trusted: put the server's PEM certificate in the connection's `userProvidedServerCertificate` ([TLS server certificate validation](https://docs.databricks.com/ingestion/lakeflow-connect/tls-server-certificate-validation)), passing every option on `connections update`. `trustServerCertificate` turns validation off: only on a test source, with the user's OK.

## SQL Server

- **Change tracking or CDC, per table, on the primary.** Before choosing, read the [integrated pipeline](https://docs.databricks.com/ingestion/lakeflow-connect/sql-server-integrated-pipeline) page for which one the connector reads when both are on and which SCD types each supports, and follow it. Then confirm through the connection that each table has the capture its SCD type needs:

  ```sql
  SELECT * FROM remote_query('<connection>', database => '<database>', query => "
    SELECT s.name AS sch, t.name AS tbl, t.is_tracked_by_cdc,
           CASE WHEN ct.object_id IS NULL THEN 0 ELSE 1 END AS change_tracking
      FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id
      LEFT JOIN sys.change_tracking_tables ct ON ct.object_id = t.object_id")
  ```

| Symptom | Fix |
|---|---|
| `TRUNCATE` on a change-tracking table: destination keeps the rows, or `INGESTION_GATEWAY_UNTRACEABLE_TABLE_MODIFICATION` | Full refresh after every `TRUNCATE`; prefer `DELETE` |
| Drop and recreate a change-tracking table: no error, old rows stay | Full refresh the table |
| Drop and recreate a CDC table: `INGESTION_GATEWAY_CDC_LOG_TRUNCATED`, then `MANAGED_INGESTION_CANNOT_CHANGE_SOURCE_FOR_EXISTING_DESTINATION_TABLE` | Map it to a new `destination_table` |
| Column rename on a change-tracking table: `CDC_INCOMPATIBLE_SCHEMA_CHANGES.COLUMNS_ADDED_AND_DELETED` | Full refresh, or `auto_full_refresh_policy` |
| `GENERIC_SNAPSHOT_FAILURE`: "VIEW DATABASE PERFORMANCE STATE permission denied" | Grant it, then start a new update |
| Rows after a schema change never arrive, no error | Keep `VIEW DATABASE STATE` on the login |
| `INGESTION_GATEWAY_DDL_OBJECTS_MISSING` | Run the DDL objects script it names, full refresh the table |
| A capture instance disabled or changed: changed rows stop, no error | Full refresh the table |
| `INGESTION_GATEWAY_CDC_LOG_TRUNCATED` with capture on | Capture-instance name differs in case from the table: use the exact name from `cdc.change_tables`, full refresh |
| Error 8649, or a snapshot that ends short with no error | Remove the query governor / `REQUEST_MAX_CPU_TIME_SEC` limit on the login |

## PostgreSQL

Read the PostgreSQL pipeline page for who creates the publication and the slot; when it's the user, give the SQL to the user or their DBA.

- **Order:** publication, `bundle deploy`, stop the new gateway (it fails with `INGESTION_GATEWAY_CDC_NOT_ENABLED` while the slot is missing), create the slot, start the gateway, run the ingestion pipeline.
- **One publication and one slot per pipeline pair,** named so you can tell which pipeline owns them; never shared. After deleting a pipeline, check `pg_replication_slots` for its slot and drop your own by name.
- **Source:** `wal_level = logical` (RDS/Aurora `rds.logical_replication = 1`); `REPLICA IDENTITY FULL` unless the table has a primary key and no unbounded TOAST-able column; a finite `max_slot_wal_keep_size` (`-1` lets a stalled slot fill the disk); `max_replication_slots` / `max_wal_senders` for one slot per pair. On 16+ a non-superuser admin may not `SET ROLE` to a role it created: create the slot as a role with `REPLICATION`.

The ingestion pipeline names the slot and publication in `source_configurations` (`postgres.slot_config`), as the PostgreSQL pipeline page's example shows.

| Symptom | Fix |
|---|---|
| `INGESTION_GATEWAY_CDC_NOT_ENABLED`: "Logical replication slot <slot> doesn't exist" | Create the slot; if it was dropped, also full refresh the tables |
| `INGESTION_GATEWAY_PG_SLOT_IS_INVALIDATED` (`wal_status = 'lost'`) | Create the slot again, full refresh |
| `wal_level` "should be set to 'logical'"; the update can sit in `INITIALIZING` | Set it, restart the server |
| "needs FULL REPLICA IDENTITY" (a TOAST-able column under `DEFAULT`, also after adding one) | `REPLICA IDENTITY FULL`, full refresh |
| "The server does not support SSL" | Turn on `ssl` at the source |
| An added generated column never appears; a widened `NUMERIC` lands rounded | Plain column, or compute downstream; full refresh after the type change |
| `INGESTION_GATEWAY_DDL_NOT_SUPPORTED` after a column change | Full refresh, or `auto_full_refresh_policy` |
| Source disk filling | A stopped or deleted gateway's slot holds WAL: restart it, or drop the slot |

## MySQL

- `binlog_format=ROW`, `binlog_row_image=FULL`; "Leave binlog_row_value_options empty" ([MySQL setup](https://docs.databricks.com/ingestion/lakeflow-connect/mysql-source-setup)). Keep the binlog well past the schedule interval: `MYSQL_BINLOG_FILE_DELETED` needs a full refresh.
- The pipeline reads the binlog as a client: `SHOW REPLICAS` is empty, `SHOW PROCESSLIST` has a `Binlog Dump` row per reader. Don't `KILL` it on a shared source.
- No `Snapshot of ... COMPLETED` event for MySQL tables: read the snapshot flow's `COMPLETED` in `flow_progress`, or count rows.
- `MISSING_TABLE_IN_SOURCE` with no privilege message: `SELECT` was revoked on that table. A dropped table fails every update at analysis ("Failed to resolve flow"): remove it from the pipeline. `ADD COLUMN ... FIRST/AFTER` lands at the end.

## Oracle

Integrated CDC or query-based. A create request takes every field the page marks required (such as `channel`). Read the [Oracle pipeline](https://docs.databricks.com/ingestion/lakeflow-connect/oracle-integrated-pipeline) page for which service `source_catalog` is on a multi-tenant database, and follow it; the connection's `service_name` is the same, with the domain suffix when `DB_DOMAIN` is set (`Missing service_name option in the connection` without it). `user` uppercase (`C##LFC_USER`). `remote_query` runs in the connection's service: a second connection for a PDB's tables.

| Symptom | Fix |
|---|---|
| `INGESTION_GATEWAY_INTERNAL_ERROR` ("cannot recover"); `ORA-65040` on the source | `source_catalog` or the connection's service differs from what the Oracle pipeline page names: change it to match |
| `ORA-01045`, then `ORA-00942` on `V_$` views, then table `SELECT` (they show one at a time) | The grants in [Configure Oracle](https://docs.databricks.com/ingestion/lakeflow-connect/oracle-integrated-setup), including its setup procedures (`GRANT_SELECT_PERMISSIONS`), and each object the message names |
| 0 tables found; the update stays `INITIALIZING`, snapshots `SCHEDULED` | Dictionary grants missing |
| `MISSING_TABLE_IN_SOURCE`: "No catalog or schema was found for replication" | `SET CONTAINER` and `CONTAINER_DATA=ALL` for the common user |
| `INGESTION_GATEWAY_ORACLE_ARCHIVE_LOG_FILES_UNAVAILABLE`, update may still complete | Raise recovery-area retention, full refresh the tables; read flow events, not the update status |
| `INGESTION_GATEWAY_TABLE_SKIPPED_DUE_TO_UNSUPPORTED_COLUMN_DATA_TYPE` (`XMLTYPE`) | Remove the table |
| `INGESTION_GATEWAY_TABLE_DROPPED`, every table stops | Remove the dropped table |
| `NUMBER` without precision lands as a string | Cast downstream, or declare a precision |
