# Multi-Notebook Workloads

Step 1.5 of the migration workflow in [SKILL.md](../SKILL.md#step-15-handle-multi-notebook-workloads): the full procedure. For `bundle_config.py` upstream sources, see [Multi-source enumeration](multi-source-enumeration.md).

If the workload spans more than one user notebook (exclude `_resources/` setup notebooks from the count), process them **one at a time** rather than all at once. The agent's context window is finite, and trying to hold the full source of an 8-notebook job in active context while doing analysis, fixes, and migration triggers autocompact thrashing (Claude Code) or equivalent context-overflow failures in other clients.

**Procedure**:

1. **Enumerate first.** List every user notebook with its path. Do not read the bodies in full yet beyond a few lines for orientation.
   - **Check for `bundle_config.py` (H4).** If the source tree contains a `bundle_config.py`, parse it and follow any upstream-source declarations (git URLs, S3 paths, `init_scripts`, `git_source`, or custom upstream-repo declarations). Clone or fetch each referenced repo into a sibling location and include its notebooks in the enumeration. List "external sources" as a first-class artifact category in the migration plan. Without this step, multi-source demos (e.g., `dbt-on-databricks` references the upstream `dbt-databricks-c360` repo) get mis-enumerated and the real task notebooks are missed.
2. **For each notebook, in order**:
   a. Read its full source.
   b. Run the Step 2 Analyze checklist scoped to this notebook only.
   c. Record a structured summary in your response or to a scratch file, then drop the raw source from active working memory. The summary must include:
      - `notebook_path` (relative)
      - `detected_patterns[]` (pattern IDs from this skill's catalog)
      - `blockers[]` (Category-3 patterns this notebook hits, if any)
      - `migration_steps[]` (concrete fixes ordered)
      - `unmigratable` (bool — true if any blocker has no workaround)
   d. If you have a writable scratch directory (`~/.databricks-migration-skill/scratch/<run-id>/findings/`), persist the summary as `<notebook-basename>.json`. This frees the source from context safely. If not, keep the summary compact in conversation history.
3. **Synthesize.** After all notebooks have a summary, produce the unified migration plan from the summaries alone. Apply fixes notebook-by-notebook, never re-reading the original source unless required to resolve an ambiguity in a summary.
4. **Failure Reporting.** Trigger the Failure Reporting Protocol exactly once per workload, not once per notebook. The `detected_patterns` array in the report aggregates across all notebooks; `notebook_characteristics` uses summed line counts and the union of language/streaming/ML flags.

**Threshold guidance**: apply this procedure when the user notebook count is ≥ 3, or when individual notebooks exceed ~5KB of source. For 1–2 small notebooks the single-pass workflow in Steps 2–4 is fine.

**Anti-pattern**: do NOT attempt a "merge all notebooks into one big file" or "read all notebooks, then act in one mega-turn" strategy. Both defeat the purpose by reintroducing the original context-pressure problem.
