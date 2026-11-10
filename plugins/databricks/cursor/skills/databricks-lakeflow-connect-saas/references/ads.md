# Ads connectors: Google Ads, Meta Ads, LinkedIn Ads, Reddit Ads, TikTok Ads

- **Entity tables** (campaigns, ad groups, ads, creatives) are fully refreshed every update, with no SCD type 2 unless the connector's overview page says it supports it. **Report tables** (impressions, clicks, spend) are incremental, with a lookback window that re-reads recent days.
- **`source_schema` is the ad account ID** for most tables, never `default`, except: LinkedIn `account_history` (a multi-account pipeline repeats the table list per account ID) and Reddit `ad_account` are under `default`.
- Read `<key>-concepts` (Google, Meta, LinkedIn, Reddit) before choosing tables.

## Google Ads

`connector_options.google_ads_options`, on the schema or the table:
- `sync_start_date`: first load of report tables. Default two years back, no maximum.
- `lookback_window_days`: default 30. Conversions change for up to 90 days: match the attribution window (for example `60`).
- `manager_account_id`: the 10-digit MCC ID, one per pipeline. The docs say it isn't supported in bundles; set it from a notebook.

```json
{"schema": {"source_schema": "<customer-account-id>",
            "destination_catalog": "main", "destination_schema": "google_ads",
            "connector_options": {"google_ads_options": {"lookback_window_days": 60}}}}
```

## Meta Ads

- No UI during Beta: CLI, API, SDKs or bundles. Facebook Ads only, not Instagram Ads.
- `ad_insights` takes `connector_options.meta_ads_options`: `level` (`account`, `campaign`, `adset`, `ad`), `start_date` (`YYYY-MM-DD`, within 36 months), `breakdowns` and `action_breakdowns` (lists such as `["age", "gender", "country"]`).
