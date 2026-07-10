---
name: databricks-app-resources
description: "Attach, update, and reason about resources on a Databricks App — apps create-update, update_mask/merge semantics, and app-level vs space-level resources. Use when connecting a resource (Lakebase/Postgres, SQL warehouse, serving endpoint, secret, UC volume, Genie space) to an app or changing an app's resources."
compatibility: Requires databricks CLI (>= v0.294.0)
metadata:
  version: "0.1.0"
parent: databricks-apps
---

# Databricks App Resources

How a Databricks App gets access to resources, and how to attach or change them. For a resource type's own fields, load that type's skill (e.g. **`databricks-lakebase`** for Lakebase/Postgres).

## Resource levels: app vs space

A resource is usable by an app only once it's **attached**, at one of two levels:

- **App-level** — scoped to this app's service principal; **changeable from here** (with consent).
- **Space-level** — inherited from the app's space, **shared by every app in the space**; change it in the Databricks UI only.

Which levels a type supports is fixed by the type (a type may support one or both); the app's effective access is the **union**. To tell a resource's level, check `databricks apps get <APP_NAME>`:

- listed under `resources` ⇒ **app-level**
- appears only under `effective_resources` (the app+space union) but **not** under `resources` ⇒ **space-level**

Don't assume space-level and refuse without checking.

## Updating an app's resources: `apps create-update`

Always use **`databricks apps create-update`** to change an app's resources or config — for **every** app. The older `databricks apps update` is **legacy** and should not be used (it can't change resources for an app in a space). Pass everything in `--json` (only `APP_NAME` is positional); the body is `{"update_mask": "...", "app": {...}}`:

```bash
databricks apps create-update <APP_NAME> --json @update.json --profile <PROFILE>   # waits; --no-wait to return early
```

⚠️ **`update_mask` scopes the change to the fields you list, and each listed field is replaced wholesale (not item-merged).** With `update_mask=resources` the entire `resources` array is replaced — read the app's current resources and **merge** your new entry in, or you'll detach the rest. Fields you don't list (e.g. `user_api_scopes`) are left untouched.

```bash
# read the current resources first, then submit the full (merged) array
databricks apps get <APP_NAME> --profile <PROFILE>
```

Body shape (one entry per attached resource; the typed key + fields depend on the resource type):

```json
{
  "update_mask": "resources",
  "app": {
    "resources": [
      { "name": "<key>", "<resource_type>": { "...type-specific fields...": "", "permission": "<PERMISSION>" } }
    ]
  }
}
```

## Wiring a resource at scaffold time

To create a **new** app already wired to a resource, scaffold with the resource's feature and `--set` keys:

```bash
databricks apps init --name <APP_NAME> --features <feature> \
  --set "<key>=<value>" ... --run none --profile <PROFILE>
```

The feature name, the `--set` keys, and how to obtain the identifier values are resource-specific — get them from that resource's skill (for Lakebase, see **`databricks-lakebase`**).

## Resources on a deployed app: ownership & deploy-first

A deployed app runs as its **service principal**, not as you. The SP can only use objects it has been granted or that it **created itself** — so when an app creates objects inside a resource (e.g. a database schema), the SP must own them.

- **Deploy before running locally.** Deploy first so the SP creates and owns its objects; running locally as yourself first can leave objects user-owned, which the SP then can't use — the #1 source of permission errors.
- If an object ends up user-owned, the fix (grant vs. recreate) is resource-specific — see that resource's skill (for Lakebase schemas, **`databricks-lakebase`**).

## Resource-type fields

The typed sub-object differs per resource type. For **Lakebase/Postgres** — the `postgres` resource key, `branch`/`database` paths, scaffold `--set` keys, and schema ownership — see the **`databricks-lakebase`** skill.

## Consent

Never create, modify, or detach a resource without the user's explicit go-ahead. `create-update` runs as the user, so it fails if they lack permission — then give step-by-step Databricks UI instructions instead.
