# Model Serving: Calling ML Endpoints from Apps

Use Model Serving when your app needs **AI features** — chat, inference, embeddings, or predictions from a Databricks Model Serving endpoint. For analytics dashboards, use `config/queries/` instead. For persistent storage, use Lakebase.

## When to Use

| Pattern | Use Case | Data Source |
|---------|----------|-------------|
| Analytics | Read-only dashboards, charts, KPIs | SQL Warehouse |
| Lakebase | CRUD operations, persistent state, forms | PostgreSQL (Lakebase) |
| Model Serving | Chat, AI features, model inference | Serving Endpoint |
| Multiple | Dashboard with AI features or persistent state | Combine as needed |

## Scaffolding

Check if the `serving` plugin is available in the AppKit template:

```bash
databricks apps manifest --profile <PROFILE>
```

**If the manifest includes a `serving` plugin:**

```bash
databricks apps init --name <APP_NAME> --features serving \
  --set "serving.serving-endpoint.name=<ENDPOINT_NAME>" \
  --run none --profile <PROFILE>
```

**If no `serving` plugin** (add manually to an existing app):

Use the `databricks-model-serving` skill to create a serving endpoint first, then follow the resource declaration and tRPC patterns below.

## Resource Declaration

Add the serving endpoint resource to `databricks.yml`:

```yaml
resources:
  apps:
    my_app:
      resources:
        - name: my-model-endpoint
          serving_endpoint:
            name: <ENDPOINT_NAME>
            permission: CAN_QUERY          # auto-granted to SP on deploy
```

Add environment variable injection in `app.yaml`:

```yaml
env:
  - name: SERVING_ENDPOINT
    valueFrom: serving-endpoint
```

The injected value is the endpoint **name** (not a URL). Use it in server-side code to call the endpoint.

## tRPC Pattern

Always use tRPC for model serving calls — do NOT call endpoints directly from the client.

```typescript
// server/server.ts (or server/trpc.ts)
import { initTRPC } from "@trpc/server";
import { getExecutionContext } from "@databricks/appkit";
import { z } from "zod";
import superjson from "superjson";

const t = initTRPC.create({ transformer: superjson });
const publicProcedure = t.procedure;

export const appRouter = t.router({
  queryModel: publicProcedure
    .input(z.object({ prompt: z.string() }))
    .query(async ({ input: { prompt } }) => {
      const { serviceDatabricksClient: client } = getExecutionContext();
      const response = await client.servingEndpoints.query({
        name: process.env.SERVING_ENDPOINT,
        messages: [{ role: "user", content: prompt }],
      });
      return response;
    }),
});
```

## Client-side Pattern

```typescript
// client/src/components/ChatComponent.tsx
import { trpc } from "@/lib/trpc";

const result = await trpc.queryModel.query({ prompt: userInput });
const answer = result.choices?.[0]?.message?.content;
```

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|---------|
| `PERMISSION_DENIED` on query | SP missing CAN_QUERY | Declare `serving_endpoint` resource in `databricks.yml` with `permission: CAN_QUERY` |
| `SERVING_ENDPOINT` env var empty | Missing env injection | Add `valueFrom: serving-endpoint` to `app.yaml` env section |
| 504 Gateway Timeout | Inference exceeds 120s proxy limit | Reduce `max_tokens` or use WebSockets — see [Platform Guide](../platform-guide.md) |
| `getExecutionContext` undefined | Called outside AppKit server context | Ensure call is inside a tRPC procedure on the server side |
