# Advanced Widget Specifications

Advanced visualization types for AI/BI dashboards. For core widgets (text, counter, table, bar, line, pie), see [1-widget-specifications.md](1-widget-specifications.md).

---

## Area Chart

- `version`: **3**
- `widgetType`: "area"
- Same structure as line chart - useful for showing cumulative values or emphasizing volume

> Time-series area charts benefit from a `vertical-line` annotation marking a meaningful event (launch, incident, holiday) — turns a generic trend into a readable story. See [Annotations in 1-widget-specifications.md](1-widget-specifications.md#annotations-event-markers).

```json
"spec": {
  "version": 3,
  "widgetType": "area",
  "encodings": {
    "x": {"fieldName": "week_start", "scale": {"type": "temporal"}},
    "y": {
      "scale": {"type": "quantitative"},
      "fields": [
        {"fieldName": "revenue_usd", "displayName": "Revenue"},
        {"fieldName": "returns_usd", "displayName": "Returns"}
      ]
    }
  }
}
```

---

## Scatter Plot / Bubble Chart

- `version`: **3**
- `widgetType`: "scatter"
- `x`, `y`: quantitative or temporal
- `size`: optional quantitative field for bubble size
- `color`: optional categorical or quantitative for grouping

```json
"spec": {
  "version": 3,
  "widgetType": "scatter",
  "encodings": {
    "x": {"fieldName": "return_date", "scale": {"type": "temporal"}},
    "y": {"fieldName": "daily_returns", "scale": {"type": "quantitative"}},
    "size": {"fieldName": "count(*)", "scale": {"type": "quantitative"}},
    "color": {"fieldName": "category", "scale": {"type": "categorical"}}
  }
}
```

---

## Combo Chart (Bar + Line)

Combines bar and line visualizations on the same chart - useful for showing related metrics with different scales.

- `version`: **1**
- `widgetType`: "combo"
- `y.primary`: bar chart fields
- `y.secondary`: line chart fields

> Mark meaningful events with a `vertical-line` annotation when the x-axis is temporal. See [Annotations in 1-widget-specifications.md](1-widget-specifications.md#annotations-event-markers).

```json
{
  "widget": {
    "name": "revenue-and-growth",
    "queries": [{
      "name": "main_query",
      "query": {
        "datasetName": "metrics_ds",
        "fields": [
          {"name": "daily(date)", "expression": "DATE_TRUNC(\"DAY\", `date`)"},
          {"name": "sum(revenue)", "expression": "SUM(`revenue`)"},
          {"name": "avg(growth_rate)", "expression": "AVG(`growth_rate`)"}
        ],
        "disaggregated": false
      }
    }],
    "spec": {
      "version": 1,
      "widgetType": "combo",
      "encodings": {
        "x": {"fieldName": "daily(date)", "scale": {"type": "temporal"}},
        "y": {
          "scale": {"type": "quantitative"},
          "primary": {
            "fields": [{"fieldName": "sum(revenue)", "displayName": "Revenue ($)"}]
          },
          "secondary": {
            "fields": [{"fieldName": "avg(growth_rate)", "displayName": "Growth Rate"}]
          }
        },
        "label": {"show": false}
      },
      "frame": {"title": "Revenue & Growth Rate", "showTitle": true}
    }
  },
  "position": {"x": 0, "y": 0, "width": 12, "height": 5}
}
```

---

## Choropleth Map

Displays geographic regions colored by aggregate values. Requires a field with geographic names (state names, country names, etc.).

- `version`: **1**
- `widgetType`: "choropleth-map"
- `region`: defines the geographic area mapping
- `color`: quantitative field for coloring regions

```json
"spec": {
  "version": 1,
  "widgetType": "choropleth-map",
  "encodings": {
    "region": {
      "regionType": "mapbox-v4-admin",
      "admin0": {
        "type": "value",
        "value": "United States",
        "geographicRole": "admin0-name"
      },
      "admin1": {
        "fieldName": "state_name",
        "type": "field",
        "geographicRole": "admin1-name"
      }
    },
    "color": {
      "fieldName": "sum(revenue)",
      "scale": {"type": "quantitative"}
    }
  }
}
```

### Region Configuration

**Region levels:**
- `admin0`: Country level - use `"type": "value"` with fixed country name
- `admin1`: State/Province level - use `"type": "field"` with your data column
- `admin2`: County/District level

**Geographic roles:**
- `admin0-name`, `admin1-name`, `admin2-name` - match by name
- `admin0-iso`, `admin1-iso` - match by ISO code

**Supported countries for admin1:** United States, Japan (prefectures), and others.

### Color Scale for Maps

> **Note**: Unlike other charts, choropleth-map supports additional color scale properties:
> - `scheme`: color scheme name (e.g., "YIGnBu")
> - `colorRamp`: custom color gradient
> - `mappings`: explicit value-to-color mappings

---

## Forecast Line (with `AI_FORECAST`)

Overlays a model prediction on top of historical data — historical line continues into a future band with upper/lower confidence bounds.

- `version`: **1**
- `widgetType`: "forecast-line"
- The dataset SQL produces the original series **plus** three forecast columns: a point forecast, upper band, lower band. Spark's built-in `AI_FORECAST` table function generates them. Full `AI_FORECAST` params (grouping, intervals, `global_floor`/`global_cap`, seasonality) → [databricks-ai-functions / 3-ai-forecast.md](../../databricks-ai-functions/references/3-ai-forecast.md).

### Dataset SQL pattern

> **Always exclude the current (in-progress) bucket from the historical series.** If you aggregate weekly and today is Tuesday, the current week's bucket is only 2 days of data — the line drops off a cliff right before the forecast starts. Filter with `WHERE bucket_start < DATE_TRUNC('<grain>', current_date())` using the **same grain as the aggregation**.

```sql
WITH actuals AS (
  SELECT DATE_TRUNC('WEEK', opened_at) AS opened_at, COUNT(*) AS count
  FROM support_cases
  -- Drop the partial-elapsed bucket. Grain MUST match the DATE_TRUNC above —
  -- weekly aggregation → exclude current week; monthly → exclude current month.
  WHERE DATE_TRUNC('WEEK', opened_at) < DATE_TRUNC('WEEK', current_date())
  GROUP BY 1
),
dates AS (
  SELECT MAX(opened_at) AS max_d, MIN(opened_at) AS min_d FROM actuals
),
forecast AS (
  SELECT opened_at, count_forecast, count_upper, count_lower, CAST(NULL AS BIGINT) AS count
  FROM AI_FORECAST(
    TABLE(actuals),
    horizon    => (SELECT max_d + MAKE_DT_INTERVAL(
                    CAST(FLOOR(DATEDIFF(max_d, min_d) * 0.5) AS INT), 0, 0, 0) FROM dates),
    time_col   => 'opened_at',
    value_col  => 'count',
    parameters => '{"global_floor": 0}'   -- counts can't go negative; clamps the forecast + lower band at 0
  )
),
bridge AS (
  -- One-row "seam" that carries the last actual value into the forecast columns
  -- so the historical line and the forecast band visually connect instead of breaking
  -- with a gap at the boundary.
  SELECT a.opened_at,
         a.count        AS count_forecast,
         a.count        AS count_upper,
         a.count        AS count_lower,
         a.count
  FROM actuals a
  JOIN dates d ON a.opened_at = d.max_d
)
SELECT opened_at, CAST(NULL AS BIGINT) AS count_forecast, CAST(NULL AS BIGINT) AS count_upper, CAST(NULL AS BIGINT) AS count_lower, count FROM actuals
UNION ALL SELECT opened_at, count_forecast, count_upper, count_lower, count FROM bridge
UNION ALL SELECT opened_at, count_forecast, count_upper, count_lower, count FROM forecast
```

Three CTEs:
- **`actuals`** — historical series (`count` populated, forecast columns NULL).
- **`forecast`** — `AI_FORECAST` output (forecast columns populated, `count` NULL).
- **`bridge`** — a **single row at the last actual timestamp** with the actual value duplicated into all three forecast columns. Without it, the historical line and the forecast band have a visible gap at the boundary; with it, they connect smoothly.

> **The final `SELECT`s must list columns explicitly, in the same order, in every branch.** `SELECT * FROM actuals` (2 cols) `UNION ALL SELECT * FROM forecast` (5 cols) errors out with `NUM_COLUMNS_MISMATCH`. Project the same 5-column shape from every CTE — fill NULLs where a branch doesn't have a value (and `CAST(NULL AS <type>)` so the types align).

The `horizon` expression projects forward 50% of the historical range. Tune the multiplier (0.5 → 1.0 for "predict as far as we've seen") to taste.

**If you switch the aggregation grain, update both `DATE_TRUNC` calls.** They must match — a daily x-axis with a weekly cutoff filter would still show the cliff. Common pairings:

| Aggregation `DATE_TRUNC` | Cutoff filter |
|---|---|
| `'DAY'` | `WHERE event_ts < DATE_TRUNC('DAY', current_timestamp())` — drops today |
| `'WEEK'` | `WHERE DATE_TRUNC('WEEK', event_ts) < DATE_TRUNC('WEEK', current_date())` — drops current week |
| `'MONTH'` | `WHERE DATE_TRUNC('MONTH', event_ts) < DATE_TRUNC('MONTH', current_date())` — drops current month |
| `'QUARTER'` / `'YEAR'` | same shape with that grain |

### Widget spec

```json
"spec": {
  "version": 1,
  "widgetType": "forecast-line",
  "encodings": {
    "x": {"fieldName": "opened_at", "scale": {"type": "temporal"}},
    "y": {
      "scale":           {"type": "quantitative"},
      "original":        {"fieldName": "count",          "displayName": "Cases"},
      "prediction":      {"fieldName": "count_forecast", "displayName": "Forecast"},
      "predictionUpper": {"fieldName": "count_upper"},
      "predictionLower": {"fieldName": "count_lower"}
    }
  },
  "annotations": [ /* vertical-line for known events — same shape as in 1-widget */ ],
  "frame": {"showTitle": true, "title": "Case Volume Forecast"}
}
```

> Annotations (`vertical-line`) work on forecast-line — useful for marking known seasonal events (holidays, releases) inside both the historical window and the prediction band. Shape documented in [1-widget-specifications.md](1-widget-specifications.md#annotations-event-markers).

---

## Pivot

A cross-tab — dimensions on rows AND columns, measures in cells. Supports per-cell conditional styling (heat-map-style).

- `version`: **3**
- `widgetType`: "pivot"
- For multi-dimensional aggregations like "category × priority", supports drill-down totals, and is the right widget for cohort retention (see end of section).

```json
"spec": {
  "version": 3,
  "widgetType": "pivot",
  "encodings": {
    "rows": [
      {"fieldName": "industry"},
      {"fieldName": "customer_segment", "total": {"show": true}}
    ],
    "columns": [
      {"fieldName": "category"},
      {"fieldName": "Priority Level", "total": {"show": true}}
    ],
    "cell": {
      "type": "multi-cell",
      "fields": [
        {
          "fieldName": "count(*)",
          "cellType": "text",
          "style": {
            "type": "basic",
            "rules": [
              {"condition": {"operand": {"type": "data-value", "value": "30"}, "operator": ">="},
               "backgroundColor": {"hex": "#FF7E5C"}},
              {"condition": {"operand": {"type": "data-value", "value": "20"}, "operator": ">="},
               "backgroundColor": {"themeColorType": "visualizationColors", "position": 0}},
              {"condition": {"operand": {"type": "data-value", "value": "15"}, "operator": ">="},
               "backgroundColor": {"themeColorType": "visualizationColors", "position": 6}}
            ]
          }
        }
      ]
    }
  },
  "frame": {"showTitle": true, "title": "Cases by Category × Priority"}
}
```

For a **continuous color gradient** instead of explicit thresholds, set `cell.fields[].cellType: "color-scale"` and drop the `style.rules`. The gradient auto-fits to min/max in the cell values.

**Sort by cell values** (e.g., put the highest-volume column first) — useful for cohort tables:
```json
"columns": [{
  "fieldName": "category",
  "scale": {"type": "categorical", "sort": {"by": "cell", "field": {"index": 0}}}
}]
```
`"by": "cell-reversed"` flips the order. `field.index` picks which value field to sort by when there are multiple.

> **Cohort retention charts** are built as a `pivot`. Rows = cohort date, columns = period offset (`0`, `1 year`, `2 years`…), cell = retention ratio with `cellType: "color-scale"`. There is no separate `cohort` widget type.

---

## Histogram

Frequency distribution. The bin width is set in the **widget's field expression**, not in the dataset SQL.

- `version`: **3**
- `widgetType`: "histogram"

```json
"queries": [{
  "name": "main_query",
  "query": {
    "datasetName": "ds_cases",
    "fields": [
      {"name": "bin(time_to_resolution_hours, binWidth=2)",
       "expression": "BIN_FLOOR(`time_to_resolution_hours`, 2)"},
      {"name": "count(*)", "expression": "COUNT(`*`)"}
    ],
    "disaggregated": false
  }
}],
"spec": {
  "version": 3,
  "widgetType": "histogram",
  "encodings": {
    "x": {"fieldName": "bin(time_to_resolution_hours, binWidth=2)",
          "scale": {"type": "quantitative"}},
    "y": {"fieldName": "count(*)", "scale": {"type": "quantitative"}}
  },
  "frame": {"showTitle": true, "title": "Resolution Time Distribution"}
}
```

The field `name` (and the widget's `fieldName`) is the readable `bin(col, binWidth=N)` label; the underlying `expression` uses `BIN_FLOOR(\`col\`, N)` — a Lakeview field-expression, not raw SQL.

---

## Sankey

Flow between two or more stages. Each stage is a categorical field; the value is a quantitative aggregate.

- `version`: **1**
- `widgetType`: "sankey"

```json
"spec": {
  "version": 1,
  "widgetType": "sankey",
  "encodings": {
    "value":  {"fieldName": "count(*)"},
    "stages": [
      {"fieldName": "channel"},
      {"fieldName": "reopened_flag", "displayName": "Reopened"}
    ]
  },
  "frame": {"showTitle": true, "title": "Channel → Reopen flow"}
}
```

Add more `stages` entries for multi-step flows (e.g., funnel-with-attribution: `source → channel → outcome`).

---

## Heatmap

Color-intensity grid: x-axis categorical, y-axis categorical, color = numeric aggregate. Useful for "X by Y" matrices.

- `version`: **3**
- `widgetType`: "heatmap"

```json
"spec": {
  "version": 3,
  "widgetType": "heatmap",
  "encodings": {
    "x":     {"fieldName": "priority",  "scale": {"type": "categorical"}, "axis": {"hideTitle": true}},
    "y":     {"fieldName": "ship_mode", "scale": {"type": "categorical"}, "axis": {"hideTitle": true}},
    "color": {"fieldName": "sum(order_count)",
              "scale": {"type": "quantitative",
                        "colorRamp": {"mode": "scheme", "scheme": "viridis"}}}
  },
  "frame": {"showTitle": true, "title": "Order count by priority × ship mode"}
}
```

Heatmap limit: 64K rows / 10MB. For larger data, pre-aggregate to a smaller grid.

`axis.hideTitle: true` (shown above) drops the redundant "priority" / "ship_mode" axis labels — the row/column headers already tell you what they are. Same trick works on any x/y axis encoding (line, bar, heatmap, pivot) when the column name is obvious from context.

---

## Funnel

Stage-by-stage conversion: how many users / records make it from step 1 to step N.

- `version`: **1**
- `widgetType`: "funnel"

```json
"spec": {
  "version": 1,
  "widgetType": "funnel",
  "encodings": {
    "x":     {"fieldName": "stage"},
    "y":     {"fieldName": "count",      "scale": {"type": "quantitative"}},
    "color": {"fieldName": "count"}
  },
  "frame": {"showTitle": true, "title": "Signup funnel"}
}
```

Dataset SQL typically returns one row per stage, with an ordering column. Use `ORDER BY stage_order` in the SQL to guarantee top-to-bottom visualization.

---

## Box

Distribution summary (median, quartiles, whiskers, outliers). Compare distributions across categories.

- `version`: **1**
- `widgetType`: "box"

```json
"spec": {
  "version": 1,
  "widgetType": "box",
  "encodings": {
    "x": {"fieldName": "return_flag",      "displayName": "Return flag"},
    "y": {"fieldName": "l_extendedprice",  "displayName": "Extended price",
          "scale": {"type": "quantitative"}}
  },
  "frame": {"showTitle": true, "title": "Price distribution by return flag"}
}
```

---

## Waterfall

Cumulative effect of positive/negative deltas — useful for P&L bridges, MoM revenue walks, factor decomposition.

- `version`: **1**
- `widgetType`: "waterfall"

```json
"spec": {
  "version": 1,
  "widgetType": "waterfall",
  "encodings": {
    "x": {"fieldName": "monthly(date_col)",
          "expression": "DATE_TRUNC(\"MONTH\", `date_col`)"},
    "y": {"fieldName": "sum(amount)", "scale": {"type": "quantitative"}}
  },
  "frame": {"showTitle": true, "title": "Monthly P&L"}
}
```

Dataset typically returns one row per period with signed values (positive contributions, negative deductions).

---

## Gantt

Horizontal bars over a temporal or quantitative range, grouped by a row hierarchy. Use a Gantt chart for project schedules, workflows, and other events with a start and end.

- `version`: **1**
- `widgetType`: `"gantt"`
- `rows`: one or more categorical fields, ordered from the outermost group to the innermost
- `range.start` and `range.end`: fields of the same type, with a `temporal` or `quantitative` scale
- `color` and `values`: optional. `values` adds columns beside each bar.

```json
{
  "widget": {
    "name": "project-schedule",
    "queries": [{
      "name": "main_query",
      "query": {
        "datasetName": "project_tasks",
        "fields": [
          {"name": "task", "expression": "`task`"},
          {"name": "subtask", "expression": "`subtask`"},
          {"name": "min(start_at)", "expression": "MIN(`start_at`)"},
          {"name": "max(end_at)", "expression": "MAX(`end_at`)"},
          {"name": "first(status)", "expression": "FIRST(`status`)"}
        ],
        "disaggregated": false
      }
    }],
    "spec": {
      "version": 1,
      "widgetType": "gantt",
      "encodings": {
        "rows": [
          {"fieldName": "task", "displayName": "Task"},
          {"fieldName": "subtask", "displayName": "Subtask"}
        ],
        "range": {
          "start": {"fieldName": "min(start_at)", "displayName": "Start"},
          "end": {"fieldName": "max(end_at)", "displayName": "End"},
          "scale": {"type": "temporal"}
        },
        "color": {
          "fieldName": "first(status)",
          "displayName": "Status",
          "scale": {"type": "categorical"}
        }
      },
      "frame": {"showTitle": true, "title": "Project schedule"}
    }
  },
  "position": {"x": 0, "y": 0, "width": 12, "height": 6}
}
```

Every encoded `fieldName` must match a field selected by the widget query. The start and end fields must have the same data type. For numeric ranges such as completion intervals, change the range scale to `{"type": "quantitative"}`.

See the [Gantt chart documentation](https://docs.databricks.com/aws/en/dashboards/manage/visualizations/types#gantt).

---

## Path Map

Draws routes, tracks, transit lines, rivers, and other connected paths over a basemap.

- `version`: **1**
- `widgetType`: `"path-map"`
- `path.pathType`: `"geometry"` for a stored line, `"longitude-latitude-sequence"` for ordered coordinates, or `"geometry-point-sequence"` for ordered Point geometries
- `color` and `linePattern`: optional categorical fields that also partition sequence rows into separate paths
- `size`: optional data-driven line width for stored geometry paths; sequence paths use constant `mark.size`
- `extra`: optional tooltip fields

For waypoint data, set `disaggregated: true` so each point remains available to the renderer. `order` determines how the points within each route are connected.

```json
{
  "widget": {
    "name": "delivery-routes",
    "queries": [{
      "name": "main_query",
      "query": {
        "datasetName": "route_waypoints",
        "fields": [
          {"name": "route_name", "expression": "`route_name`"},
          {"name": "latitude", "expression": "`latitude`"},
          {"name": "longitude", "expression": "`longitude`"},
          {"name": "stop_order", "expression": "`stop_order`"}
        ],
        "disaggregated": true
      }
    }],
    "spec": {
      "version": 1,
      "widgetType": "path-map",
      "encodings": {
        "path": {
          "pathType": "longitude-latitude-sequence",
          "latitude": {"fieldName": "latitude"},
          "longitude": {"fieldName": "longitude"},
          "order": {"fieldName": "stop_order"}
        },
        "color": {
          "fieldName": "route_name",
          "displayName": "Route",
          "scale": {"type": "categorical"}
        }
      },
      "frame": {"showTitle": true, "title": "Delivery routes"}
    }
  },
  "position": {"x": 0, "y": 0, "width": 12, "height": 7}
}
```

For waypoints stored as `Point` geometries, use `geometry-point-sequence` with GeoJSON query output and an ordering field:

```json
"queries": [{
  "name": "main_query",
  "query": {
    "datasetName": "route_waypoints",
    "fields": [
      {"name": "route_name", "expression": "`route_name`"},
      {"name": "point_geojson", "expression": "ST_ASGEOJSON(`point_geometry`)"},
      {"name": "stop_order", "expression": "`stop_order`"}
    ],
    "disaggregated": true
  }
}],
"spec": {
  "version": 1,
  "widgetType": "path-map",
  "encodings": {
    "path": {"pathType": "geometry-point-sequence", "fieldName": "point_geojson", "order": {"fieldName": "stop_order"}},
    "color": {"fieldName": "route_name", "scale": {"type": "categorical"}}
  }
}
```

For a `GEOMETRY` or `GEOGRAPHY` column containing `LineString` or `MultiLineString` values, use a geometry path instead:

```json
"queries": [{
  "name": "main_query",
  "query": {
    "datasetName": "transit_lines",
    "fields": [{"name": "route_geojson", "expression": "ST_ASGEOJSON(`route_geometry`)"}],
    "disaggregated": true
  }
}],
"spec": {
  "version": 1,
  "widgetType": "path-map",
  "encodings": {
    "path": {"pathType": "geometry", "fieldName": "route_geojson"}
  }
}
```

The geometry query field must use `ST_ASGEOJSON(...)`; a bare geometry column produces an empty map. For grouped geometry, supported expressions include `ST_ASGEOJSON(FIRST(...))`, `ST_ASGEOJSON(LAST(...))`, and `ST_ASGEOJSON(ST_UNION_AGG(...))`.

See the [path map documentation](https://docs.databricks.com/aws/en/dashboards/manage/visualizations/types#path-map) and [path map options](https://docs.databricks.com/aws/en/dashboards/manage/visualizations/maps#path-map-options).

---

## Non-native visualizations

`word-cloud` and `sunburst` are not native AI/BI dashboard widget types. Do not emit either value as `widgetType`. For a sunburst or a word-cloud-like visualization, use [`custom-vega-viz`](6-custom-visualizations.md) when Vega-Lite can express the requested result; otherwise explain the limitation and choose a supported visualization.
