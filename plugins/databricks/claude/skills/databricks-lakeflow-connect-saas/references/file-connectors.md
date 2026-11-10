# File connectors: SharePoint, Google Drive, OneDrive, SFTP

- **Managed connector or the file APIs.** Each of the three also reads with `read_files`, `spark.read`, `COPY INTO` or Auto Loader, for transformations during ingestion: [Google Drive](https://docs.databricks.com/ingestion/google-drive), [OneDrive](https://docs.databricks.com/ingestion/onedrive), [SharePoint](https://docs.databricks.com/ingestion/sharepoint). The rest of this page is the managed connector.
- **SFTP** is not an `ingestion_definition` pipeline: Auto Loader (`format("cloudFiles")`) loads `sftp://<user>@<host>:<port>/<path>` with a UC connection holding the credentials ([SFTP](https://docs.databricks.com/ingestion/sftp)); pipeline code: **databricks-pipelines**.
- **Pick the auth method first**; each has its own `-source-setup` page.
- **Files: one row per file.** `file_ingestion_options.format: BINARYFILE` puts the bytes in a content column; CSV, JSON and Excel can be parsed into Delta tables instead.
- **The FILE type (Beta)** stores a governed reference in place of the bytes: `channel: PREVIEW`, `format: FILE`, and `table_configuration.table_properties` `databricks.filespace-preview: /Volumes/<catalog>/<schema>/<volume>/`.
- Objects name the source in `connector_options`, with no `source_schema`/`source_table`: `sharepoint_options`, `gdrive_options` (Google Drive), `onedrive_options`. Each takes `entity_type: FILE` and `url`, the site, folder or file address as the browser shows it.
- **SharePoint lists (Beta):** `entity_type: LIST`, one list or every list in a site, no `file_ingestion_options`; copy the shape from the `sharepoint-pipeline` page's list section.

```yaml
resources:
  pipelines:
    sharepoint_files:
      name: sharepoint_files
      catalog: main
      schema: sharepoint_raw
      channel: PREVIEW
      ingestion_definition:
        connection_name: <sharepoint-connection>
        objects:
          - table:
              destination_catalog: main
              destination_schema: sharepoint_raw
              destination_table: site_files
              connector_options:
                sharepoint_options:
                  entity_type: FILE
                  url: <sharepoint-site-url>
                  file_ingestion_options:
                    format: BINARYFILE
                    schema_evolution_mode: NONE
```

- **RAG:** `ai_parse_document` on the ingested `inline_content` column (`sharepoint-rag`); see **databricks-ai-functions**.
- OneDrive reads one user's OneDrive for Business **My files**. Sites, team sites and shared libraries: SharePoint.
- OneDrive in a bundle needs Databricks CLI 1.23.0 or later: older CLIs drop `onedrive_options` without an error.
