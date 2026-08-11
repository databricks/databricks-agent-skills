# Custom Visualizations (Vega-Lite)

Use a **custom visualization** when the chart you need isn't a built-in
`widgetType` (matrix/grid heatmap, radar, gauge, bullet, sunburst, radial,
network/tree). It renders a [Vega-Lite](https://vega.github.io/vega-lite/) spec
(public preview). It is **not** arbitrary HTML/JS/D3 — only Vega-Lite grammar.

For built-in charts, prefer those (simpler, cross-filter, theme-aware by
default). Reach for custom viz only when no built-in type fits.

## `custom-vega-viz`

- `version`: **1**
- `widgetType`: "custom-vega-viz"
- `query.disaggregated`: **true** (custom viz is row-level, not aggregated)

Unlike built-in widgets — where `encodings` maps fields to axes — a custom-viz
widget carries the entire chart as a Vega-Lite spec, and its `encodings` block is
just the **flat list of columns** the spec is allowed to read:

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
      "jsonSpec": {"type": "vega-lite", "spec": "{\"$schema\": \"https://vega.github.io/schema/vega-lite/v5.json\", ... }"},
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
- `spec.encodings.fields` must list **every** column the spec reads, and each
  `fieldName` must match a `query.fields[].name`.
- `spec.data.queryName` must match the query `name` (`"main_query"`).

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

## Verified limitations

- **Cross-filtering breaks LAYERED specs.** A `databricks_mark_selection` point
  selection `params` block works on a **single-view** spec, but on a **layered**
  spec (e.g. `rect` + `text`) the custom-viz renderer fails: the canvas stays at
  Vega's 300×150 default and the chart renders **blank, with no console error**.
  Confirmed with the bare param, param + highlight conditions, and explicit
  pixel width/height — all blank. For click-to-filter, keep the spec
  single-view (drop the text layer, rely on tooltips) or drive the drill-down
  outside the dashboard. Built-in widgets sharing a dataset still cross-filter
  normally.
- **No treemap** — Vega-Lite doesn't support it.
- **Image marks**: inline base64 `data:` URIs only, ≤ 37 KB, PNG/JPEG/WebP. No
  remote/relative/SVG/expression-driven image URLs.

## Theme-aware styling

Custom viz inherits the dashboard theme (fonts, gridlines, transparent
background) automatically. For theme-aware mark colors, reference the `colors`,
`mode`, and `dashboardTheme` signals inside a Vega expression — e.g.
`{"expr": "colors.markHighlightColor"}` or
`{"expr": "dashboardTheme.visualizationColors[0]"}`.

## Deploy

No different from any dashboard: bare table names in `queryLines`, and
`--dataset-catalog` / `--dataset-schema` on `lakeview create` / `update` (see
the main SKILL.md workflow). Full Vega-Lite spec galleries (gauge, radar,
bullet, sunburst, radial, phylogenetic tree) are in the Databricks docs:
"Custom visualizations in AI/BI dashboards".
