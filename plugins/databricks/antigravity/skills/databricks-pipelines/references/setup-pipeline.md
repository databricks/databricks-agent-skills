# Setup Pipeline

## IMPORTANT: Use managed ingestion for connector sources

When a Lakeflow Connect managed connector supports the source (SaaS and database sources such as Salesforce, Workday, ServiceNow, Google Analytics, SQL Server, PostgreSQL, MySQL, or Oracle; and file sources such as Google Drive and SharePoint), prefer managed ingestion over Spark Declarative Pipeline (SDP) code — it handles API rate limiting, incremental sync, and schema changes for the user. Use the `databricks-lakeflow-connect` skill (databases) or the `databricks-lakeflow-connect-saas` skill (SaaS and file sources) for source-specific setup, permissions, and troubleshooting.

## Overview

This reference guides you through setting up a new Spark Declarative Pipeline (SDP) with initial datasets. Pick the project workflow (bundle or rapid CLI iteration) from the Project Setup section of the skill first; this reference covers which datasets to build and in what order.

## Workflow Overview

Follow this sequence when setting up a new pipeline:

```
1. Gather Data Context
   └── Read the table or run SQL sample queries to understand source data
       ├── Identify schema, columns, data types
       └── Understand data relationships

2. Present the user with two options:
   └── They can propose a pipeline architecture of their choice
   └── You can propose a medallion architecture (Bronze → Silver → Gold) pipeline, which they can iteratively modify
       └── If they use your template, ask for confirmation or modifications

3. Create Pipeline Files
   └── Write one file per dataset with its transformation code in the project's source folder
   └── Ensure all dependencies are implemented correctly
   └── Keep an existing pipeline's language; for a new pipeline follow the language guidance in the skill's Project Setup section

4. Validate and run
   └── Deploy or upload the files, start a dry run, fix any errors, then run an update and check that it completes
```

## Key Principles

### Batch file creation

- Write all dataset files before the first dry run instead of validating after each file; a dry run checks the whole graph at once.
