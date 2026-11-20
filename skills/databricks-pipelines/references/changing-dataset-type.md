# Changing a dataset's type

Changing an existing dataset's type (e.g., streaming table to materialized view, or vice versa) is NOT possible without the user first manually dropping the existing table. Full refresh does NOT help.

When a user asks to change a dataset type:

1. **Explain the limitation clearly**: you MUST explicitly tell the user that changing the type on the same name will cause the pipeline to **FAIL** unless the existing table is manually dropped first. Also state that full refresh does NOT help. Do not skip or soften this warning.
2. **Rename the dataset (this is the primary action, not in-place)**: unless the user indicated they already dropped the existing table, the default fix is to define the converted dataset under a different name (e.g., append a suffix or use a descriptive new name) so both the old and new datasets can coexist. The old dataset will become inactive once it is no longer defined in code. Never just change the type on the same name — that is not a valid end state and will fail.
3. **Find and fix EVERY downstream reference**: after renaming, the old name must no longer appear anywhere except as the brand-new dataset's definition. Inspect every pipeline file, locate each reference to the old name, and edit it to point at the renamed dataset, fixing any read that becomes invalid for the new source type:
   - A materialized view is **not a valid streaming source**. If the renamed dataset is now a materialized view, any downstream that read it via `spark.readStream` / `STREAM(...)` MUST switch to a batch read (`spark.read` / `FROM` without `STREAM`), or the pipeline will fail.
   - A streaming table can be read with either a batch or streaming read, so converting a source to a streaming table does not by itself force a downstream read change — a downstream batch read keeps working.

   Only the dataset whose type is changing gets renamed. Do NOT rename a downstream dataset or change its type — leave its own name and definition alone and edit only its reference to the renamed dataset (and that reference's read semantics, per above). Note that for `@dp.table` / `@dlt.table` the read method is what determines the type, so changing such a downstream's read would flip it between streaming table and materialized view.

   A passing dry run or update does NOT prove the downstreams were rewired: the original table may still physically exist and silently satisfy a stale reference to the old name. Confirm by inspecting the code that no downstream still points at the old name — do not rely on a green run.

4. **Offer manual drop as a follow-up**: explicitly suggest as a follow-up action that the user can drop the old table themselves and then rename the new dataset back to the original name if they prefer.
