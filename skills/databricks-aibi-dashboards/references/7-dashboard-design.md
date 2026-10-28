# Dashboard Design: Data Profiling, Theme, Layout, Genie Link, Data Variance

Design detail for [SKILL.md](../SKILL.md). Load it when profiling data and building the JSON: probe the data, set the theme on every dashboard, lay out the 12-column grid, optionally link a Genie space, and check metric variance before choosing trend charts.

## Profiling the data

Step 2 of the creation workflow in [SKILL.md](../SKILL.md): after `discover-schema`.

Sample rows alone don't tell you what to build. you can write aggregate SQL through `databricks experimental aitools tools query --warehouse <WH> "..."` to probe typically:

- **Cardinality** of candidate grouping columns → decides chart color-group vs. table (≤8 distinct values for charts, see SKILL.md § Cardinality & Readability).
- **Top categorical values** → populates filter options and chart legends meaningfully.
- **Numeric distribution** (min/max/avg/percentiles) → decides KPI with delta vs. trend chart (flat metrics shouldn't be line charts, see [Data Variance](#data-variance-considerations) below).
- **Trend viability** at daily/weekly/monthly grain → picks the right trend granularity.
- **Story confirmation** — run the aggregations you plan to put in the dashboard and check they're not flat, empty, or uninteresting. Fix the query or adjust the story before moving on.

Fan out independent probes in one call — pass several positional SQLs (and/or repeated `--file`) and they run in parallel (default `--concurrency 8`):

```bash
DATABRICKS_WAREHOUSE_ID=<WH> databricks experimental aitools tools query --output json \
  "SELECT COUNT(*) FROM catalog.schema.orders" \
  "SELECT region, COUNT(*) FROM catalog.schema.orders GROUP BY region ORDER BY 2 DESC LIMIT 10" \
  "SELECT MIN(ts), MAX(ts) FROM catalog.schema.orders"
```

- **`--output json` is mandatory** in multi-query mode. Returns one object per statement: `{sql, state, rows, error}`; failures are per-statement (`state: "FAILED"`), others still succeed.
- ⚠️ **Don't trust the exit code** (a failed statement can still exit `0`) — gate on each object's `state != "SUCCEEDED"`.

## Planning example

Step 4 of the creation workflow in [SKILL.md](../SKILL.md):

| Widget | Type | Dataset | Has filter field? |
|--------|------|---------|-------------------|
| Revenue KPI | counter | ds_sales | ✓ date, region |
| Trend Chart | line | ds_sales | ✓ date, region |
| Top Products | table | ds_products | ✗ no date | 
...

## Design Best Practices

Apply unless user specifies otherwise:
- **Global date filter**: When data has temporal columns, add a date range filter. Most dashboards need time-based filtering.
- **KPI time bounds**: Use time-bounded metrics that enable period comparison (MoM, YoY). Unbounded "all-time" totals are less actionable.
- **Value formatting**: Format values based on their meaning — currency with symbol, percentages with %, large numbers compacted (K/M/B).
- **Chart selection**: Match cardinality to chart type. Few distinct values → bar with color grouping (or pie if you really want a snapshot); many values → table.

## Theme & Color

Top-level `uiSettings.theme` controls colors, fonts, and widget chrome across every widget on the dashboard. Without it, the dashboard inherits the workspace default and looks generic. **Set the full block on every dashboard you create** — a coherent palette is the single highest-impact polish item.

Mental model — **60/30/10 rule** mapped to theme keys: **60% neutral** = canvas/widget/border backgrounds (set `widgetBorderColor = widgetBackgroundColor` to hide borders); **30% secondary** = `fontColor` + `visualizationColors` (the content weight); **10% accent** = `selectionColor` for filters / tabs / active selections — pick something distinct from text and palette; a safe-blue around `#2272B4` matches the hyperlink convention and works as a default.

```json
{
  "datasets": [...],
  "pages": [...],
  "uiSettings": {
    "theme": {
      "canvasBackgroundColor": {"light": "#FCFCFC", "dark": "#1F272D"},
      "widgetBackgroundColor": {"light": "#FFFFFF", "dark": "#11171C"},
      "fontColor":             {"light": "#11171C", "dark": "#E8ECF0"},
      "selectionColor":        {"light": "#2272B4", "dark": "#8ACAFF"},
      "visualizationColors": [
        "#FFA600", "#FF7054", "#DE5582", "#995495",
        "#4E5185", "#1D425C", "#99DDB4"
      ],
      "widgetHeaderAlignment": "LEFT"
    }
  }
}
```

**Theme keys** (mechanics):

- `visualizationColors`: ordered palette every chart series and category mapping cycles through. **Positions are 0-indexed**: `position: 0` = first color (`#FFA600` above), `position: 6` = seventh (`#99DDB4`). Length 5–8 is typical.
- Background / font / selection colors take `light` + `dark` pairs; the dashboard auto-selects based on viewer mode.
- `fontColor` also drives the **counter number color** — counters have no per-widget color, so this is the only lever for them (it colors every counter's value on the dashboard, not per-tile).
- `widgetHeaderAlignment`: `"LEFT"` (default), `"CENTER"`, or `"RIGHT"`. Optional top-level: `fontFamily` (e.g. `"Space Grotesk"`, `"Inter"` — sans-serif keeps dense data readable; don't override per widget) and `widgetCornerRadius` (integer px, e.g. `12` for rounded corners; `0` or omit = square).
- Per-widget color references (charts only): `{"themeColorType": "visualizationColors", "position": N}` (0-indexed) to pin to a palette slot, or `{"hex": "#FF0000"}` for an exact color outside the palette. **Counters do NOT support a per-widget color** — a `color` on a counter's `value` renders the widget as "unsupported widget definition"; color counters via `fontColor` above.

**Palette-design rules** (this is what separates a polished dashboard from a noisy one):

1. **One coherent color family per dashboard, distinct across the suite.** Walk **across hues** (e.g., amber → coral → pink → purple → navy), not one color faded toward white — a single-hue lightness ramp reads as one color and the viewer can't tell categories apart. Adjacent stops must be visually distinct: if you squint and two blur into one, push them further apart. Single-hue ramps are for **quantitative** widgets only (`colorRamp.mode: "custom-sequential"`), never for `visualizationColors`.
2. **Pin semantic colors as literal hex, outside the palette.** "Bad" = a warm coral (e.g. `#FF7E5C`), "good" = a calm teal/green. Use `color.scale.mappings` with a bare hex string — `{"value": "Critical", "color": "#FF7E5C"}` — **not** `{"hex": "..."}` or `themeColorType: position` (both are silently dropped on chart widgets). Reuse the good-teal that's already in the palette so it never clashes.
3. **Color non-categorical widgets explicitly so they join the family.** Maps & heatmaps: `colorRamp.mode: "custom-sequential"` with `{start, end}` from the family (if directional: `start` = bad color, `end` = good color). Forecast / multi-series: pin per-series via `color.scale.mappings` keyed on `displayName` (actual = solid family color, forecast = contrast/alert, threshold = muted tone). Counters (incl. sparkline counters) take **no** per-widget color — their number color comes from the theme's `fontColor`; do NOT set `value.color` (it renders "unsupported widget definition").
4. **"Lighter / more pastel" tweak**: nudge all stops up in lightness *together*; don't recolor individual ones. Re-sync the pinned semantic hex values; keep enough contrast on the alert color that it still reads as a warning.

**Starter palettes** (pick one and adapt — extend to 7-8 stops if needed; semantic red/green stay as literal hex per rule 2):

```
#094074  #3C6997  #5ADBFF  #FFDD4A  #FE9000
#003F5C  #594E90  #BC4C96  #FF5F66  #FFA600
#4A8CC7  #F59770  #FFD84A  #F0E09E  #6DD980
#440154  #3B528B  #21918C  #5EC962  #FDE725
#4E79A7  #F28E2C  #E15759  #76B7B2  #59A14F
#0072B2  #E69F00  #009E73  #CC79A7  #D55E00
#0D0887  #7E03A8  #CC4778  #F89441  #F0F921
#6929C4  #1192E8  #005D5D  #9F1853  #FA4D56
```

~4-5% of viewers have color blindness (mostly red/green). Rows 4 and 6 above (viridis, Okabe-Ito) are CB-safe by design; verify customized palettes via simulator (Adobe Color, `colorbrewer2.org`). Don't put red and green adjacent, and rely on lightness contrast — not hue alone — between adjacent stops.

## Layout (12-Column Grid, No Gaps)

**Every page must include `"layoutVersion": "GRID_V1"`** alongside `pageType`.

```json
{
  "name": "overview",
  "displayName": "Overview",
  "pageType": "PAGE_TYPE_CANVAS",
  "layoutVersion": "GRID_V1",
  "layout": [...]
}
```

Each widget has a position: `{"x": 0, "y": 0, "width": 4, "height": 4}`

**Pick the subdivision based on the audience.** The 12-column grid divides cleanly into 3, 4, or 6 columns: a 3-column layout (each widget `width: 4`) reduces cognitive load and fits an executive overview; a 4-column (`width: 3`) is the all-rounder; a 6-column (`width: 2`) packs the most density for technical / operations dashboards where the reader is hunting through many metrics at once.

**Default rule**: each row should fill width=12 exactly — no gaps. Once you're confident with the grid, you can stagger heights across columns (a tall widget on the left paired with several shorter ones on the right) so the two halves don't share row boundaries — see [4-examples.md](4-examples.md#layout-12-col-grid) for the pattern. Start with strict rows; relax only when the stagger reads better visually.

```
CORRECT:                            WRONG:
y=0: [w=12]                         y=0: [w=8]____  ← gap!
y=1: [w=4][w=4][w=4]  ← fills 12    y=1: [w=2][w=2][w=2][w=2]__  ← gap!
y=4: [w=6][w=6]       ← fills 12
```

**Recommended widget sizes:**

| Widget Type | Width | Height | Notes |
|-------------|-------|--------|-------|
| Text header | 12 | 1 | Full width; use SEPARATE widgets for title and subtitle |
| Counter/KPI | 4 | **3-4** | **NEVER height=2** - too cramped! |
| Line/Bar/Area chart | 6 | **5-6** | Pair side-by-side to fill row |
| Pie chart | 6 | **5-6** | Needs space for legend |
| Full-width chart | 12 | 5-7 | For detailed time series |
| Table | 12 | 5-8 | Full width for readability |

**Standard dashboard structure:**
```text
y=0:  Title (w=12, h=1) - Dashboard title (use separate widget!)
y=1:  Subtitle (w=12, h=1) - Description (use separate widget!)
y=2:  KPIs (w=4 each, h=3) - 3 key metrics side-by-side
y=5:  Section header (w=12, h=1) - "Trends" or similar
y=6:  Charts (w=6 each, h=5) - Two charts side-by-side
y=11: Section header (w=12, h=1) - "Details"
y=12: Table (w=12, h=6) - Detailed data
```

## Linking a Genie Space (Optional)

To add an "Ask Genie" button to the dashboard, or to link a genie space/room with an ID, add `uiSettings.genieSpace` to the JSON (alongside `theme` if you have one):

```json
"uiSettings": {
  "theme": { /* ... */ },
  "genieSpace": {
    "isEnabled": true,
    "overrideId": "your-genie-space-id-here",
    "enablementMode": "ENABLED"
  }
}
```

> **Genie is NOT a widget.** Link via `uiSettings.genieSpace` only. There is no `"widgetType": "assistant"`.

## Data Variance Considerations

Before creating trend charts, check if the metric has enough variance to visualize meaningfully:

```sql
SELECT MIN(metric), MAX(metric), MAX(metric) - MIN(metric) as range FROM dataset
```

If the range is very small relative to the scale (e.g., 83-89% on a 0-100 scale), the chart will appear nearly flat. Consider:
- Showing as KPI with delta/comparison instead of chart
- Using a table to display exact values
- Adjusting the visualization to focus on the variance
