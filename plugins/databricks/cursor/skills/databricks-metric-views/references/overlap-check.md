# Overlap check with existing metric views

Step 3 of the [advisor workflow](metric-view-advisor.md) runs this check before it builds suggestions, against the inventory from [Step 1](metric-view-advisor.md#step-1--discover-existing-metric-views-do-this-first-always). Step numbers below are the advisor's.

**If existing metric views were discovered during the "Discover existing metric views" step**, you MUST check for semantic overlap before generating suggestions. This prevents duplicate views from accumulating across multiple runs. **Skip this check entirely if** no existing metric views were found (fresh schema).

**Comparison logic — for each candidate metric view you are about to suggest:**

1. **Match by source table** — Find all existing metric views that use the same source table (fully qualified name). This is the primary overlap signal.
2. **Compute dimension overlap** — For each pair with the same source table, compare dimension `expr` values. Normalize before comparing (strip whitespace, lowercase, ignore trivial differences like a `source.` prefix); count dimensions with matching expressions even if names differ: `dim_overlap = matching_dims / max(candidate_dims, existing_dims)`.
3. **Compute measure overlap** — Same approach for measure `expr` values: `measure_overlap = matching_measures / max(candidate_measures, existing_measures)`.
4. **Compute coverage score** — `(matching_dims + matching_measures) / (candidate_dims + candidate_measures)`:
   - **High (>=70%)**: Existing view already covers most of what you'd suggest
   - **Medium (40-69%)**: Significant overlap worth addressing
   - **Low (<40%)**: Mostly new content — minimal overlap
5. **If multiple existing views overlap the same candidate**, pick the one with the **highest coverage score** as the primary comparison target. Mention the others as additional duplicates.

**For each overlap with coverage >= 40%, present a report to the user:**

> **Overlap detected:** Your suggested `lineitem_metrics` overlaps with existing `lineitem_analytics`
>
> | | Suggested | Existing | Shared |
> |--|-----------|----------|--------|
> | Source | ...lineitem | ...lineitem | Same |
> | Dimensions | 15 | 16 | 12 |
> | Measures | 14 | 15 | 10 |
> | **Coverage** | | | **73%** |
>
> **Only in suggested (new):** Order Date, Order Month, Total Tax Amount, Avg Unit Price
> **Only in existing:** Ship Instruction, Container, Average Discount, Total Tax
>
> | # | Action | What happens |
> |---|--------|-------------|
> | 1 | **Extend existing** `lineitem_analytics` | Add the missing items to the existing view (recommended) |
> | 2 | **Replace** with `lineitem_metrics` | Drop old view, deploy new one instead |
> | 3 | **Create alongside** | Keep both (you accept the overlap) |
> | 4 | **Skip** | Don't create a lineitem-level view at all |

**How each resolution affects downstream steps:**
- **Extend (1):** Step 4 generates a `CREATE OR REPLACE VIEW` under the **existing** view name, merging all existing dimensions/measures with the new ones. Preserve existing `comment`, `synonyms`, and `display_name` values.
- **Replace (2):** Step 4 generates a `CREATE OR REPLACE VIEW` under the **new** name. Step 6 also drops the old view after deploying the new one.
- **Create alongside (3):** Normal suggestion flow — no changes.
- **Skip (4):** Remove this candidate from the suggestions entirely.

**Auto-create mode behavior:**
- Coverage >= 70% → automatically choose **Extend existing** (safest default — no duplication, no data loss)
- Coverage 40-69% → **pause and ask the user** (too ambiguous to auto-resolve)
- Coverage < 40% or no source-table match → automatically **create alongside**

**Review-first mode:** Always present the overlap report and wait for the user's response for every overlap >= 40%.

> **Safety:** Only "Extend" or "Replace" an existing metric view when the user explicitly chooses that option for the reported overlap. Never drop or overwrite a pre-existing view the user did not ask you to change.

After resolving all overlaps, return to [Step 3](metric-view-advisor.md#step-3--suggest-metric-views) and build the final suggestions list reflecting the user's choices.
