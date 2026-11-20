# Sources

Every source below is read with the same Auto Loader / `read_files()` code — see
`references/file-ingestion/auto-loader.md` for the dataset shapes. Only the path and the access
mechanism change per source.

| Source | Path | Access | Managed connector? |
| --- | --- | --- | --- |
| Unity Catalog volume | `/Volumes/<catalog>/<schema>/<volume>/...` | `READ VOLUME` on the volume | No — use this reference |
| Cloud object storage | `s3://...`, `abfss://...`, `gs://...` | A UC **external location** covering the prefix | No — use this reference |
| SFTP | `sftp://<host>:<port>/<absolute_path>` | A UC **connection** (SFTP) | No — use this reference |
| Google Drive | Google Drive URL | A UC **connection** (Google Drive) | **Yes — prefer managed** |
| SharePoint | SharePoint URL | A UC **connection** (SharePoint) | **Yes — prefer managed** |
| OneDrive (Beta) | OneDrive for Business URL | A UC **connection** (OneDrive) | No — use this reference |

## Creating the UC connection

SFTP, Google Drive, SharePoint, and OneDrive read through a Unity Catalog connection passed with
`databricks.connection`. Using one requires `USE CONNECTION` (standard access mode) or
`MANAGE CONNECTION` (dedicated access mode). If the user does not have one yet, do not stall:
tell them to create it, then write the code with the connection name they choose.

- Create it from **Catalog > External locations > Connections > Create connection**, choosing the
  connection type (SFTP, Google Drive, SharePoint, or OneDrive), which needs `CREATE CONNECTION`.
- Authentication differs by type:
  - **SFTP:** private key or password.
  - **Google Drive:** a Google Cloud OAuth client (client ID and secret, scope
    `https://www.googleapis.com/auth/drive.readonly`) and a Google sign-in.
  - **SharePoint:** Microsoft Entra ID OAuth with `Sites.Read.All` or `Sites.Selected`.
  - **OneDrive:** a Microsoft sign-in consenting to `Files.Read.All`.
- For Google Drive and SharePoint, the managed connector setup creates the same kind of
  connection, and a code-first pipeline can reuse it.

## Unity Catalog volumes

Use a volume path when the user's files are in a volume. Unity Catalog governs access, and
Auto Loader uses an optimized listing path for volumes.

```sql
CREATE OR REFRESH STREAMING TABLE raw_events
AS SELECT * FROM STREAM read_files(
  "/Volumes/main/raw/landing/events/",
  format => "json");
```

## Cloud object storage (S3, ADLS, GCS)

Cloud URLs work only when the prefix is covered by a **UC external location** (a UC
object that grants access to the prefix through a storage credential). If the read fails
with a permission or "no external location" error, the user needs an external location
on the prefix — or a volume over it. Cloud-specific Auto Loader options (file events,
notification setup) are in `references/auto-loader-python.md`.

```python
from pyspark import pipelines as dp

@dp.table()
def raw_orders():
  return (spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "parquet")
    .load("s3://acme-landing/orders/"))
```

## SFTP

Auto Loader reads SFTP servers through a UC SFTP connection (DBR 17.3+).

- Name the connection with the `databricks.connection` option (recommended, DBR 18.2+).
  The host and port in the URI must match the connection; the username is optional. If the
  option is omitted, the connector resolves the connection by matching `<username>@<host>`
  in the URI.
- The path is the **absolute** path on the server, starting from `/`.
- SFTP supports **streaming reads only** (Auto Loader / `STREAM read_files`). `spark.read`,
  batch `read_files`, and `COPY INTO` are not supported — build a streaming table, not a
  materialized view that reads SFTP directly.
- All Auto Loader options work except `cloudFiles.useNotifications`,
  `cloudFiles.useManagedFileEvents`, `cloudFiles.cleanSource`, and cloud-specific options.
- Encrypted (for example PGP) files: ingest as `binaryFile` and decrypt downstream.

```sql
CREATE OR REFRESH STREAMING TABLE sftp_orders
AS SELECT * FROM STREAM read_files(
  "sftp://sftp.example.com:22/uploads/orders/",
  `databricks.connection` => "my_sftp_conn",
  format => "csv",
  header => "true");
```

## Google Drive (prefer managed — code-first only on request)

Redirect to a managed Google Drive pipeline first (see [file-ingestion.md](../file-ingestion.md)).
For a code-first pipeline:

- Path: a Google Drive URL for a file, folder, or drive — for example
  `https://drive.google.com/drive/folders/<id>`,
  `https://docs.google.com/spreadsheets/d/<id>/edit`, `https://drive.google.com/drive/my-drive`.
- Pass the UC connection with `databricks.connection` on every read.
- Google Docs, Sheets, Slides, and Drawings are exported during ingestion (DOCX, XLSX,
  PPTX, PDF). Override with the Spark confs `fs.gdrive.format.{document,spreadsheet,presentation,drawing}.export`
  set to a Google export MIME type — for example `text/csv` for Sheets. Read an exported
  Sheet with `format => "excel"`.
- Google Drive-specific properties are in the hidden `_gdrive_metadata` column (DBR 18.1+;
  select it explicitly, preferably specific subfields such as `_gdrive_metadata.id`).
- `pathGlobFilter` filters by file name and cannot select built-in Google formats (Docs,
  Sheets, and so on); scope by folder through the URL instead.
- Google Forms, Sites, Jams, and Vids are skipped silently — expect no rows and no error for
  them.

```python
from pyspark import pipelines as dp

@dp.table()
def gdrive_pdfs():
  return (spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "binaryFile")
    .option("databricks.connection", "my_gdrive_conn")
    .option("pathGlobFilter", "*.pdf")
    .load("https://drive.google.com/drive/folders/1a2b3c4d"))
```

## SharePoint (prefer managed — code-first only on request)

Redirect to a managed SharePoint pipeline first (see [file-ingestion.md](../file-ingestion.md)).
For a code-first pipeline:

- Path: the URL of a site, subsite, document library, folder, or file — for example
  `https://mytenant.sharepoint.com/sites/Marketing/Shared%20Documents` (DBR 17.3 LTS+).
  Nested subsites, share links, and Microsoft 365 web (`Doc.aspx`) URLs need DBR 18 LTS+;
  the tenant root (with an M2M connection) and Site Pages (`.../SitePages`, `.aspx` pages)
  need DBR 19+.
- Pass the UC connection with `databricks.connection` on every read.
- One query reads one SharePoint site; write one ingestion query per site. A tenant root URL
  (DBR 19+, M2M connection) is the exception: it reads every site in one query.
- Microsoft 365 national clouds (`.sharepoint.us`, `.sharepoint-mil.us`, `.sharepoint.cn`)
  and Auto Loader `cleanSource` are not supported.
- `pathGlobFilter` matches file names only; scope by folder through the URL.
- SharePoint-specific properties are in the hidden `_sharepoint_metadata` column (DBR 18
  LTS+; select it explicitly, preferably specific subfields such as
  `_sharepoint_metadata.item_id`).
- SharePoint lists are ingested only by the managed connector (`entity_type: LIST`, Beta),
  not by `read_files()`.

```sql
CREATE OR REFRESH STREAMING TABLE sharepoint_pdfs
AS SELECT * FROM STREAM read_files(
  "https://mytenant.sharepoint.com/sites/Marketing/Shared%20Documents",
  `databricks.connection` => "my_sharepoint_conn",
  format => "binaryFile",
  pathGlobFilter => "*.pdf");
```

## OneDrive (Beta — code-first only)

Auto Loader reads a user's personal OneDrive for Business (**My files**) through a UC OneDrive
connection. OneDrive has no managed connector, so use this skill.

- Beta: a workspace admin enables the **Lakeflow Connect for OneDrive For Business** preview.
  Requires DBR 19+.
- Path: the drive root, a folder, a file, or a share link on the personal `-my` host — for example
  `https://mytenant-my.sharepoint.com/personal/user_mytenant_onmicrosoft_com/Documents`. A bare
  host URL or a non-drive path is not supported. SharePoint sites, team sites, and shared
  libraries use the SharePoint connector instead.
- The connection reads as the signed-in user, so only files that user can access are ingested.
- For large drives, `cloudFiles.readChangeFeed` = `true` uses the Microsoft Graph change feed
  instead of re-listing the drive. It requires `binaryFile`, a drive or folder path, and no
  explicit schema.
- `pathGlobFilter` matches file names only. OneDrive lists, Site Pages, and `cleanSource` are not
  supported.

```python
from pyspark import pipelines as dp

@dp.table()
def onedrive_reports():
  return (spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "binaryFile")
    .option("cloudFiles.readChangeFeed", "true")
    .option("databricks.connection", "my_onedrive_conn")
    .load("https://mytenant-my.sharepoint.com/personal/user_mytenant_onmicrosoft_com/Documents/Reports"))
```
