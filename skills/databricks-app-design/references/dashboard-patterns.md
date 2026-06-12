# Dashboard design patterns (reference catalog)

Vocabulary from Bach, Freeman, Abdul-Rahman, Turkay, Khan, Fan, Chen, "Dashboard Design
Patterns", IEEE TVCG 2023 (arXiv:2205.00757). The paper catalogs 42 patterns in 8 groups; the
working subset below covers the choices that matter most when generating a Databricks data app.
Use it to make explicit tradeoffs between **abstraction** (detail removed), **screenspace** (what
fits at once), **pages** (how many views), and **interaction** (work to reveal detail). Reducing
one parameter pressures another.

## Genres (starting points, not hard categories)
- **static** — single-page, screenfit, low-interaction overview. Status/exec glanceability. Needs strong abstraction + careful KPI selection.
- **analytic** — detailed charts, filters, drilldown. Analysts comparing facets / investigating causes. Avoid long scroll when side-by-side comparison matters.
- **magazine** — narrative embedded in editorial text. Public communication; needs written context.
- **infographic** — poster-like, expressive, slow-changing. Broad audiences; decoration only if it aids comprehension.
- **repository** — large collection of charts + metadata + downloads. Transparency/self-service; needs strong navigation or it's a chart dump.
- **embedded mini** — compact dashboard inside another product; summaries that link deeper.

## Content patterns
**Data information** (pick abstraction deliberately): detailed dataset · aggregation · filtered data · derived value (KPI/rate/trend/delta — explain derivation) · threshold (good/bad/SLA — only when defensible) · single value (pair with context).

**Meta information** (context, especially for casual/public audiences): data source · update information (freshness/cadence/lag) · data description (in/out of scope) · disclaimer (limits, missingness, caveats) · annotation (callouts for spikes/regime changes).

**Visual representations** (match to task precision): numbers (headline KPIs) · trend arrows (clarify up=good?) · pictograms (labels/counts) · gauges/progress bars (bounded progress only — *see conflict note in ibcs-notation.md*) · signature charts / sparklines (gist) · detailed charts (values/comparison/distribution) · tables (lookup/exact/exports) · text lists (events/alerts/exceptions).

## Composition patterns
**Screenspace**: screenfit · overflow (scroll) · detail-on-demand (tooltip/popover/drawer) · parameterization (filters/date-range/toggles) · multiple pages.

**Structure**: single page · hierarchical (overview→drilldown) · parallel (peer pages for comparable facets) · semantic (pages mirror domain) · open (loose; make nav clear).

**Page layout**: open (equal widgets) · stratified (headline summary above detail — good default for KPI dashboards) · table (repeated rows/cols for comparison) · grouped (related widgets with labels/proximity) · schematic (layout follows a real-world map/process).

**Interaction** (must earn its cost — don't hide critical context behind it): exploration (tooltip/brush/link) · filter-and-focus (search/filters/sliders/date pickers) · navigation (tabs/links/scroll) · personalization (reorder/resize/save).

**Color**: data encoding · semantic color (status/severity/threshold) · shared scheme (consistent across widgets/pages) · distinct scheme · emotive. Always check accessibility, redundant encoding, consistency. Remove color that doesn't encode data, clarify structure, or set mood.

## Review checklist
- Clear genre + primary audience?
- Headline numbers contextualized with trend, unit, freshness, source?
- Important comparisons visible without excessive scroll/nav?
- Hidden detail recoverable through sensible interaction?
- Filters/parameters aligned with real user questions?
- Layout communicates priority + grouping?
- Colors consistent, accessible, semantically safe?
- Data limitations, update timing, definitions visible enough?
- Curated decision aid vs. data collection — does the design match the intent?
