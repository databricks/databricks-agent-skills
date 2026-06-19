# IBCS notation & reporting rules (reference)

International Business Communication Standards (IBCS Association, https://www.ibcs.com/IBCS/) — a
notation system that makes comparable things look comparable and different things look different,
and strips visual choices that carry no meaning. Layer these notation rules **on top of** the
composition choices in dashboard-patterns.md.

## SUCCESS checklist
1. **SAY** — convey a message. Put the core finding in the title/lead, not buried below the chart.
2. **UNIFY** — semantic notation: same meaning → same shape, color, label, line style everywhere.
3. **CONDENSE** — increase information density (combine actual/plan/forecast/variance) when users need it together.
4. **CHECK** — visual integrity: don't distort axes, truncate scales misleadingly, or mix units.
5. **EXPRESS** — choose the visualization that fits the comparison task.
6. **SIMPLIFY** — remove clutter: decorative color, redundant legends, gridlines, effects, labels.
7. **STRUCTURE** — organize content into complete, non-overlapping groups in a logical order.

## Titles & messages
Title identifies subject + measure + period; state the finding when there is one.
- Weak: `Usage` · Better: `Databricks Apps Usage — Weekly Active Apps, Q2 2026` · Best: `Weekly active apps rose 18% in Q2 2026, led by internal analytics apps`

## Chart/table choice by comparison task
- Time series → horizontal line/columns, time left→right.
- Structural comparison → vertical bars or tables, sorted by value or business structure.
- Part-to-whole → stacked bars / structured tables; avoid pies unless very few categories and precision is unimportant.
- Variance vs plan/forecast/prior → variance bars/deltas with explicit good/bad notation.
- Exact lookup / dense comparison → tables with integrated bars, sparklines, deltas, clear sort.
- Single KPI → value + unit + period + target/prior comparison + freshness + trend context.

Prefer columns, bars, lines, tables.

## Semantic notation — the canonical scenario conventions
Standardize the meaning of marks across the whole report. **IBCS scenario notation:**

| Scenario | IBCS notation | In this app's tokens/components |
|---|---|---|
| Actual (AC) | **solid / filled** (darkest) | `--foreground` solid line/area |
| Previous year / prior period (PY) | **lighter solid fill** | `--muted-foreground`, lighter/dashed comparison series |
| Plan / budget / target (PL/BU) | **outlined / hollow** (or reference line) | dashed target/reference line (confirm chart support in docs) |
| Forecast (FC) | **hatched** | distinct hatched/striped fill — *not* merely "lighter shade" |

> Correction vs. the older skill: forecast is **hatched**, and **lighter-solid means previous-year**.
> Don't use "lighter shade" for forecast — it collides with the PY convention.

Other rules: arrange time horizontally, structure (categories) vertically; one highlight style for
the report's main message/exception; positive/negative variance use consistent colors/symbols with
"higher is good?" defined per metric. Color encodes scenario/category/status/variance only — never decoration.

## Scaling & integrity
Common scale for charts users compare · don't cut bar/column axes unless explicit and non-misleading
· consistent units per view · show baselines/targets when they define interpretation · make missing
data / partial periods / changed definitions visible · prefer direct labels over forcing axis/legend reading.

## Information density
Combine actual+target+forecast+variance in one aligned view when all four are needed · place
totals/subtotals/deltas/sparklines near the values they explain · small multiples for repeated
comparable entities with shared scales. Density is not clutter if notation is consistent and labels disciplined.

## Review checklist
Clear message/decision at top? · titles identify subject/measure/period? · time & structure laid
out consistently? · actual/plan/forecast/PY visually distinct **and** consistent? · good/bad variance
unambiguous per metric? · comparable charts on comparable scales? · axes/baselines/labels/units honest?
· color carries meaning? · can the user compare key values without unnecessary scroll/filter/page-switch?
· would a table communicate the result more clearly than a chart?

## Conflict resolution with dashboard-patterns.md
Where the two disagree, **IBCS wins on chart vocabulary and integrity**:
- gauges / donuts / pictograms: dashboard-patterns lists them as situational; **IBCS discourages** them — avoid unless a bounded-progress gauge is genuinely the clearest option.
- density: IBCS pushes higher density (combined scenarios) while dashboard-patterns warns of overload — resolve by **condensing only what the user compares together**, and paginating the rest.
