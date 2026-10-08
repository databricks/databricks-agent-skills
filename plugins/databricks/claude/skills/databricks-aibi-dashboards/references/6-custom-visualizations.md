# Custom Visualizations with Vega-Lite

Use standard widgets by default. Use a custom visualization when the required marks, layers, or layout cannot be expressed with standard widgets. Examples include bullet, gauge, radar, sunburst, and radial charts. These are Vega-Lite specifications inside a `custom-vega-viz` widget, not separate widget types. Standard charts remain appropriate for ordinary comparisons, trends, target annotations, and small multiples; see [Choose a Widget](../SKILL.md#choose-a-widget).

This reference covers the [widget contract](#widget-contract), a [bullet chart](#example-bullet-chart), [raw points with a rolling mean](#example-raw-points-with-a-rolling-mean), [other custom patterns](#more-custom-chart-patterns), and [cross-filtering](#cross-filtering). Custom Viz accepts Vega-Lite grammar, not arbitrary Vega, HTML, JS, or D3.

## Widget Contract

| Property | Value |
|----------|-------|
| `spec.widgetType` | `"custom-vega-viz"` |
| `spec.version` | `1` |
| `spec.encodings.fields` | Array of `{"fieldName": "stable_name"}` objects |
| `spec.data.queryName` | Name of the matching widget query, usually `"main_query"` |
| `spec.jsonSpec.type` | `"vega-lite"` |
| `spec.jsonSpec.spec` | **String containing JSON**, not a nested object |
| Vega-Lite `data` | `{"name": "databricks_query"}` |

The widget version and Vega-Lite schema version are independent. Use the Vega-Lite v6 schema for new specifications; the Databricks wrapper remains version 1.

Each input field has three matching names:

1. `widget.queries[].query.fields[].name`: the query output alias.
2. `widget.spec.encodings.fields[].fieldName`: the stable field name exposed to Vega-Lite.
3. Vega-Lite `encoding.*.field` (or a field referenced in a transform): that same stable name.

Separately, set `widget.spec.data.queryName` to the matching `widget.queries[].name` so the render spec selects the widget query.

For example, a query expression ``SUM(`revenue`)`` can be named `salesValue`; the other two locations then use `salesValue`, not `revenue` or an axis title. In expressions, use `datum.salesValue` or `datum["salesValue"]`. Fields created within Vega-Lite transforms do not need a query binding. Set chart labels using Vega-Lite `title`; custom field bindings do not use `displayName`.

Keep business logic and expensive aggregation in SQL or widget query expressions. Use `disaggregated: false` when the widget query aggregates; use `true` when supplying individual rows for Vega-Lite to plot or transform.

Unlike built-in widgets, where `encodings` maps fields to axes, a custom widget carries the chart as a Vega-Lite spec. Its `encodings` block is the flat list of input columns the spec may read:

```json
{
  "widget": {
    "name": "attack_matrix",
    "queries": [
      {
        "name": "main_query",
        "query": {
          "datasetName": "matrix_cells",
          "fields": [
            {"name": "tactic_name", "expression": "`tactic_name`"},
            {"name": "y_pos", "expression": "`y_pos`"},
            {"name": "technique_id", "expression": "`technique_id`"},
            {"name": "technique_state", "expression": "`technique_state`"}
          ],
          "disaggregated": true
        }
      }
    ],
    "spec": {
      "version": 1,
      "widgetType": "custom-vega-viz",
      "jsonSpec": {"type": "vega-lite", "spec": "{\"$schema\":\"https://vega.github.io/schema/vega-lite/v6.json\",\"data\":{\"name\":\"databricks_query\"},\"width\":\"container\",\"height\":\"container\",\"config\":{\"autosize\":{\"type\":\"fit\",\"contains\":\"padding\"}},\"mark\":\"rect\",\"encoding\":{\"x\":{\"field\":\"tactic_name\",\"type\":\"ordinal\"},\"y\":{\"field\":\"y_pos\",\"type\":\"ordinal\"},\"color\":{\"field\":\"technique_state\",\"type\":\"nominal\"}}}"},
      "encodings": {"fields": [
        {"fieldName": "tactic_name"}, {"fieldName": "y_pos"},
        {"fieldName": "technique_id"}, {"fieldName": "technique_state"}
      ]},
      "data": {"queryName": "main_query"}
    }
  },
  "position": {"x": 0, "y": 0, "width": 12, "height": 20}
}
```

**Rules that break the widget (blank / "invalid widget") if wrong:**

- `spec.jsonSpec.spec` is a **STRING** — the Vega-Lite JSON serialized to a
  string (e.g. `json.dumps(vega_spec)`), NOT a nested object.
- Inside the Vega-Lite spec, refer to the query result as
  `"data": {"name": "databricks_query"}` (this exact literal name).
- Reference columns in the spec with `"field": "colName"` or `datum.colName` /
  `datum["colName"]`.
- `spec.encodings.fields` must list **every query input column** the spec reads,
  and each `fieldName` must match a `query.fields[].name`. Vega-Lite transform
  outputs such as a calculated rolling mean do not need query bindings.
- `spec.data.queryName` must match the query `name` (`"main_query"`).

## Example: Bullet Chart

**Use case:** compare each category's actual revenue with its own target using a narrow actual-value bar over a target band and a target tick. A standard bar chart suffices for a plain comparison; Vega-Lite is useful when this layered bullet form is required.

The dataset supplies one row per category with `category`, `revenue`, and `target`. This example defines a dataset and one layout entry. Add `dataset` to the dashboard's `datasets` and `layout_entry` to a canvas page's `layout`. Test the dataset SQL using the skill's normal workflow before deployment.

```python
import json

dataset = {
    "name": "ds_sales",
    "displayName": "Sales",
    "queryLines": ["SELECT category, revenue, target FROM sales_targets"],
}

vega_lite = {
    "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
    "data": {"name": "databricks_query"},
    "width": "container",
    "height": "container",
    "config": {"autosize": {"type": "fit", "contains": "padding"}},
    "encoding": {
        "y": {"field": "categoryName", "type": "nominal", "title": "Category"},
        "x": {"type": "quantitative", "title": "Revenue", "scale": {"zero": True}},
        "tooltip": [
            {"field": "categoryName", "type": "nominal", "title": "Category"},
            {"field": "salesValue", "type": "quantitative", "format": ",.2f"},
            {"field": "targetValue", "type": "quantitative", "format": ",.2f"},
        ],
    },
    "layer": [
        {
            "mark": {"type": "bar", "opacity": 0.2, "size": 24},
            "encoding": {"x": {"field": "targetValue"}},
        },
        {
            "mark": {"type": "bar", "size": 10},
            "encoding": {"x": {"field": "salesValue"}},
        },
        {
            "mark": {
                "type": "tick", "thickness": 2, "size": 28,
                "color": {"expr": "colors.textPrimary.default"},
            },
            "encoding": {"x": {"field": "targetValue"}},
        },
    ],
}

layout_entry = {
    "widget": {
        "name": "custom-sales",
        "queries": [{
            "name": "main_query",
            "query": {
                "datasetName": "ds_sales",
                "fields": [
                    {"name": "categoryName", "expression": "`category`"},
                    {"name": "salesValue", "expression": "SUM(`revenue`)"},
                    {"name": "targetValue", "expression": "SUM(`target`)"},
                ],
                "disaggregated": False,
            },
        }],
        "spec": {
            "version": 1,
            "widgetType": "custom-vega-viz",
            "data": {"queryName": "main_query"},
            "encodings": {
                "fields": [
                    {"fieldName": "categoryName"},
                    {"fieldName": "salesValue"},
                    {"fieldName": "targetValue"},
                ],
            },
            "jsonSpec": {"type": "vega-lite", "spec": json.dumps(vega_lite)},
            "frame": {"showTitle": True, "title": "Revenue against target"},
        },
    },
    "position": {"x": 0, "y": 0, "width": 12, "height": 5},
}
```

Serialize the Vega-Lite object once into `jsonSpec.spec`, then serialize the dashboard as usual. When constructing an API request body, `serialized_dashboard` is itself a JSON string. Use `json.dumps` / `JSON.stringify` for each layer; do not manually escape quotes.

For interactive authoring, users can edit the chart through **Advanced > Custom Viz** in the dashboard editor. Its Vega-Lite editor accepts the inner JSON object text, without the widget wrapper; the **Fields** names correspond to the bindings above. For programmatic creation, use the serialized widget wrapper shown here.

## Example: Raw Points with a Rolling Mean

**Use case:** show noisy sensor readings as individual points while overlaying a smooth trend. A standard line chart suffices for an aggregated trend; custom layers allow points and a rolling-mean line to coexist in the same plot.

Create `ds_readings` with `SELECT observed_at, temperature FROM sensor_readings ORDER BY observed_at`. Reuse the widget wrapper above with this query:

```json
{
  "datasetName": "ds_readings",
  "fields": [
    {"name": "observedAt", "expression": "`observed_at`"},
    {"name": "temperature", "expression": "`temperature`"}
  ],
  "disaggregated": true
}
```

Set `spec.encodings.fields` to `[{"fieldName": "observedAt"}, {"fieldName": "temperature"}]`. Serialize this inner specification into `spec.jsonSpec.spec`:

```json
{
  "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
  "data": {"name": "databricks_query"},
  "width": "container",
  "height": "container",
  "config": {"autosize": {"type": "fit", "contains": "padding"}},
  "transform": [{
    "window": [{"op": "mean", "field": "temperature", "as": "rollingMean"}],
    "sort": [{"field": "observedAt", "order": "ascending"}],
    "frame": [-14, 0],
    "ignorePeers": true
  }],
  "encoding": {
    "x": {"field": "observedAt", "type": "temporal", "title": "Observed at"},
    "y": {"type": "quantitative", "title": "Temperature", "scale": {"zero": false}}
  },
  "layer": [
    {
      "mark": {"type": "point", "opacity": 0.3},
      "encoding": {"y": {"field": "temperature"}}
    },
    {
      "mark": {"type": "line", "strokeWidth": 3, "color": "#2272B4"},
      "encoding": {"y": {"field": "rollingMean"}}
    }
  ]
}
```

This window covers the current reading plus 14 preceding **rows**, not 15 days. The input should contain one sensor series with a deterministic observation order. For multiple sensors, expose a sensor field, add it to the window's `groupby`, and separate the rendered series. Compute time-based windows in SQL when observations are irregular. `rollingMean` is created by Vega-Lite, so it does not belong in the widget's query fields.

## Responsive sizing

Make the chart fill its widget box:

```json
"width": "container",
"height": "container",
"config": {"autosize": {"type": "fit", "contains": "padding"}}
```

## Grids, matrices, and networks: precompute positions in SQL

Vega-Lite plots marks at coordinates you provide — it does **not** compute layout
for a grid or network. Precompute positions in the dataset SQL, then render
layers. For a column-per-category matrix (e.g. an ATT&CK grid): explode the
category array, then assign a row slot with
`row_number() OVER (PARTITION BY category ORDER BY id)`; encode `x = category`
(ordinal, sorted) and `y = row_slot`, with a `rect` layer colored by a state
column and a `text` layer for the label. Compute a per-row text-color column in
SQL so labels stay legible on light fills, and zero-pad the row slot so an
ordinal `y` sorts numerically.

## More Custom Chart Patterns

Use the [Databricks custom visualization examples](https://docs.databricks.com/aws/en/dashboards/manage/visualizations/custom-visualizations#examples) for these less common layouts. Adapt their field names and serialize the inner specification with the same wrapper:

| Required visual | Inputs and custom construction | Standard alternative when the special layout is unnecessary |
|-----------------|--------------------------------|-----------------------------------------------------------|
| Gauge | One row containing actual and total; arc layers encode the ratio. Handle a zero total and out-of-range values in SQL. | Counter with comparison or a bar with a target annotation |
| Radar | One row per axis/category and series; calculate radial coordinates and layer paths, points, and labels. Keep metric scales comparable. | Grouped bar or standard faceting |
| Sunburst | Hierarchy levels and weights; precompute segment angles and ring bounds, then draw nested arcs. | Bar, pivot, or pie for flat categories |
| Treemap | Precompute `x0`, `x1`, `y0`, and `y1` rectangle bounds; draw `rect` marks with `x`/`x2` and `y`/`y2`. Vega-Lite does not calculate the treemap layout. | Standard bar or pivot for hierarchy comparisons |
| Network/tree diagram | Precomputed node and edge coordinates; layer paths, nodes, and labels. Vega-Lite does not calculate the graph layout. | Standard Sankey for weighted flows |

## Cross-Filtering

Add this to the **inner Vega-Lite specification** to filter other widgets when a mark is selected:

```json
{
  "params": [{
    "name": "databricks_mark_selection",
    "select": {"type": "point", "fields": ["categoryName"]}
  }]
}
```

The reserved parameter name must be exact. Use a `point` selection and list only configured dimension fields; aggregated measures cannot drive a cross-filter. Interval/brush selections do not drive dashboard cross-filtering. Ordinary Vega-Lite parameters with other names remain local to the visualization. The dashboard's normal dataset/filter scope still applies.

Use a single-view specification when the custom chart must drive cross-filtering. Layered specifications with `databricks_mark_selection` have rendered blank in dashboard tests, even though layered charts without the reserved selection render normally. Keep layered charts display-only unless a real dashboard test confirms the combined interaction works in the target workspace.

## Theme-aware styling

Custom viz inherits the dashboard theme (fonts, gridlines, transparent background) automatically. Explicit Vega-Lite `config` settings override those defaults. For theme-aware mark colors, use expression signals such as `{"expr": "colors.markHighlightColor"}` or `{"expr": "dashboardTheme.visualizationColors[0]"}`. `colors` tokens are already resolved for the active mode; do not index them with `[mode]`. Per-mode values under `dashboardTheme`, such as `dashboardTheme.gridLineColor[mode]`, do require it.

## Limits and Troubleshooting

- Bind to `databricks_query`. External or nested `data.url` sources (including lookup data URLs), top-level Vega-Lite `datasets`, `encoding.href`, `mark.href`, and `usermeta.embedOptions` are not supported. The dashboard's outer `datasets` array is still required.
- Image marks are allowed only with a static inline `data:image/...;base64,...` literal using PNG, JPEG/JPG, or WebP with a decoded payload no larger than 37 KB. Remote, relative, SVG, field-driven, expression-driven, and conditional image URLs are rejected.
- Vega-Lite does not calculate treemap or network layouts. Supply layout coordinates in SQL or another preprocessing step; do not assume arbitrary Vega specifications or Vega gallery examples work in Custom Viz.
- A blank chart usually means missing `data.name`, an empty `encodings.fields` array, or mismatched input names. Check the query output and all three binding locations before changing the chart.
- For parse errors, check the wrapper version, `jsonSpec.type`, and that `jsonSpec.spec` parses as JSON from a string.
- After deployment, inspect the rendered widget with the actual query results. Verify sizing, tooltips, and any cross-filter selection; successful dashboard creation alone does not validate the inner Vega-Lite chart.

Deploy using the usual dashboard workflow: bare table names in `queryLines`, and `--dataset-catalog` / `--dataset-schema` on `lakeview create` or `update`.

## Sources

- [Databricks custom visualizations](https://docs.databricks.com/aws/en/dashboards/manage/visualizations/custom-visualizations): field names, examples, resizing, themes, and cross-filtering.
- [AI/BI visualization types](https://docs.databricks.com/aws/en/dashboards/manage/visualizations/types): standard widget alternatives. Notebook and SQL editor visualization catalogs describe a different surface.
- [Vega-Lite examples](https://vega.github.io/vega-lite/examples/): adapt examples to `databricks_query` and the configured field names.
