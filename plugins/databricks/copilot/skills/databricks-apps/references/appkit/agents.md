# AppKit Agents Guide

**Pattern selection:** [AppKit Overview](overview.md). This guide covers **`agents()` plugin setup only.**

Use the `agents` plugin to host an **AI agent** (tool-using chatbot / assistant) inside an AppKit app. For fixed NL Q&A over UC tables prefer [`genie`](genie.md); reach for `agents` when the app needs an LLM that **calls tools** (SQL, files, Genie, MCP, UC functions), delegates to sub-agents, or streams a multi-turn conversation with human-in-the-loop approval.

> **Beta plugin.** Import from `@databricks/appkit/beta`, **not** the main barrel. APIs may shift between minor releases. Signatures here defer to `npx @databricks/appkit docs ./docs/plugins/agents.md`.

> **Agentic mode:** the app is scaffolded and resources are wired. **Skip** *Scaffolding*, *Adding agents to an existing app*, and any `databricks.yml` / `app.yaml` edits below. Read wired plugins + the serving endpoint from `appkit.plugins.json` / `app.yaml`; if the agent needs a plugin (or a serving endpoint) that isn't wired, **stop and tell the user** — never provision it yourself. The client patterns (`useAgentChat`, `/skill` sugar) still apply.

## Architecture

```text
User (browser) ── POST /api/agents/chat (SSE) ──▶ agents plugin ──▶ serving endpoint OR AI Gateway
               ◀── status / message / tool_call / approval_pending ◀──
                                    │
                       tool calls run as the user (OBO):
                       analytics.query, files.*, genie.*, MCP, sub-agents
```

Agents are **discovered from disk** — one folder per agent under `server/agents/<id>/`, holding `agent.md` (markdown) or `agent.ts` (code). The agent id **is the folder name** — no map to maintain. Tool calls run through the caller's OBO token, so SQL executes as the requesting user and file access respects Unity Catalog ACLs.

## Model backend — decide first

An agent needs an LLM. Two paths; pick before scaffolding:

| | **(A) Serving endpoint** | **(B) Managed Supervisor API** |
|--|---|---|
| Setup | Bind a **streaming-capable** chat endpoint | Zero endpoint — runs on Databricks AI Gateway |
| How | `DATABRICKS_SERVING_ENDPOINT_NAME` (or per-agent `endpoint:` / `model:`) | `model: DatabricksAdapter.fromSupervisorApi({ model: "..." })` |
| Best for | Custom / self-hosted models; full JS tool code | Fastest start; **hosted tools** (Genie, UC functions, Knowledge Assistants, apps) with no tool code |
| Tools | Function tools, MCP, sub-agents, hosted tools all work | **Only** `supervisorTools.*` reach the model — function tools, MCP, and local sub-agents are ignored (registration-time warning) |

**(A) must be a streaming endpoint.** Foundation Model APIs (Claude, Llama, GPT) and chat-style endpoints stream and work out of the box. A single-JSON `pyfunc` / `sklearn` endpoint does **not** stream — pointing an agent at it fails on the first turn with `Response body is null — streaming not supported`. Use **`databricks-model-serving`** to pick or create a streaming endpoint. (For a non-streaming custom model, use the `serving` plugin's `/invoke` + `useServingInvoke` instead — that is not an agent.)

**(B)** removes the serving-endpoint provisioning gate entirely — the LLM and hosted tools run server-side on Databricks. `supervisorTools.*` descriptions are **trusted application config**: never derive them from user input (prompt-injection routing sink, CWE-1427).

## Authoring an agent

Each agent is a folder under `server/agents/`. A folder is an agent only if it has an entry file; the id is the folder name.

**Markdown agent** (`server/agents/assistant/agent.md`) — prose + YAML frontmatter:

```md
---
endpoint: databricks-claude-sonnet-4-5   # or DATABRICKS_SERVING_ENDPOINT_NAME
default: true
tools:
  - plugin:analytics                       # all analytics tools
  - plugin:files: [uploads.read]           # only these
---

You are a read-only data analyst. Use the tools to answer questions.
```

**Code agent** (`server/agents/support/agent.ts`) — for inline `tool()`, sub-agents, or the Supervisor adapter:

```ts
import { createAgent, tool } from "@databricks/appkit/beta";
import { z } from "zod";

export default createAgent({                 // id = folder name "support"
  instructions: "You help customers with data and files.",
  model: "databricks-claude-sonnet-4-5",
  tools(plugins) {                            // plugins registered in createApp
    return {
      ...plugins.analytics.toolkit(),
      ...plugins.files.toolkit({ only: ["uploads.read"] }),
      get_weather: tool({
        description: "Weather for a city",
        schema: z.object({ city: z.string() }),
        execute: async ({ city }) => `Sunny in ${city}`,
      }),
    };
  },
});
```

**Markdown vs code:** markdown for prompt + plugin tools (most agents). Code when you need inline `tool()` logic, sub-agents (`agents: { ... }`), or `DatabricksAdapter.fromSupervisorApi`.

**Tools are opt-in.** An agent with no declared `tools:` gets an **empty** tool index — auto-inherit is **off by default** (turn on per-origin with `agents({ autoInheritTools: { file: true } })`, and even then only tools the plugin author marked `autoInheritable` and non-mutating spread in). Any plugin whose tools you reference must be registered in `createApp({ plugins: [...] })` — scaffold it into `--features` (see below), or the plugin throws at setup with an `Available: …` list.

## ⚠️ Code agents need a build change

**Markdown agents** are read from source at runtime — nothing to build. **Code agents** (`agent.ts`) are **not imported anywhere**, so a production bundle that only compiles `server/server.ts` emits **zero** `dist/agents/*/agent.js` and discovers **no** code agents. `npm run dev` (tsx) reads the `.ts` source directly and hides the gap — it only bites the bundled build.

Fix once with the build preset:

```ts
// tsdown.server.config.ts
import { appkitServerConfig } from "@databricks/appkit/tsdown";

export default appkitServerConfig();   // auto-detects server/agents/, adds the entry glob
```

The template ships this already. If a code agent "seems frozen" in dev, delete a stale `dist/agents` / `build/agents` — compiled output shadows source. (Markdown is never shadowed.)

## Scaffolding a new agent app

`agents` is the CLI feature name. All three of its resources are **optional** — `--features agents` scaffolds with no required `--set`.

```bash
# 1. Check manifest for agents plugin keys
databricks apps manifest --profile <PROFILE>

# 2. Scaffold. Add tool-provider plugins (analytics, files, genie, lakebase) to the union.
#    Bind a streaming serving endpoint for backend (A); omit it for backend (B).
databricks apps init --name <APP_NAME> --features agents,analytics,files \
  --set agents.agents-serving-endpoint.name=<STREAMING_ENDPOINT> \
  --run none --profile <PROFILE>

# 3. Local env + develop
cd <APP_NAME>
echo "DATABRICKS_SERVING_ENDPOINT_NAME=<STREAMING_ENDPOINT>" >> server/.env
npm install && npm run dev
```

**Do not guess** `--set` keys — derive from `databricks apps manifest`. Optional resources:

| Resource key | Env var | Purpose |
|---|---|---|
| `agents-serving-endpoint` | `DATABRICKS_SERVING_ENDPOINT_NAME` | Default streaming LLM (backend A) |
| `agents-mlflow-experiment` | `MLFLOW_EXPERIMENT_ID` | Trace agent turns + tool calls to MLflow (no-op when unset) |
| `agents-skills` | `DATABRICKS_VOLUME_AGENT_SKILLS` | UC Volume of catalog [Skills](#skills) (read-only, service principal) |

The scaffold generates a starter `server/agents/<id>/agent.md` and a chat page. Replace the agent's instructions and tools before validating.

## Adding agents to an existing app

**Markdown agent** — plugin only. Add `agents()` to `plugins` (import from `/beta`), drop `server/agents/<id>/agent.md`. No build change.

**Code agent** — also adopt `appkitServerConfig()` (see above) or the prod bundle discovers nothing.

**`server/server.ts`** — register the plugin (preserve existing plugins; add tool providers you reference):

```ts
import { createApp, server, analytics, files } from "@databricks/appkit";
import { agents } from "@databricks/appkit/beta";

await createApp({
  plugins: [server(), analytics(), files(), agents()],
});
```

**`databricks.yml` / `app.yaml`** (backend A) — wire a serving endpoint the same way any resource is wired: a `serving_endpoint` resource plus an env injection for `DATABRICKS_SERVING_ENDPOINT_NAME`. Derive exact keys from `databricks apps manifest`. Backend B needs no endpoint resource.

**`server/.env`** (local, backend A):

```dotenv
DATABRICKS_SERVING_ENDPOINT_NAME=<STREAMING_ENDPOINT>
```

## Frontend

There is **no drop-in `<AgentChat>` component** (unlike `<GenieChat>`). Build the chat UI on the **`useAgentChat` hook** — the scaffold generates a page that does exactly this.

```tsx
import { useAgentChat } from "@databricks/appkit-ui/react";

function AgentPage() {
  const { content, isStreaming, error, send } = useAgentChat({ agent: "assistant" });
  // send(message)                    — normal turn
  // send(message, { skill: "name" }) — force a skill; or type "/skill-name …" (sugar)
  return <div style={{ height: 600 }}>{/* render content, wire send() to input */}</div>;
}
```

Give the container an explicit height or the chat collapses (same gotcha as Genie). For the full hook API (events, thread history, approval handling), run `npx @databricks/appkit docs "useAgentChat"`.

## HTTP endpoints

| Route | Method | Streaming | Notes |
|-------|--------|-----------|-------|
| `/invocations` | POST | No | OpenAI Responses-compatible; **model-serving contract** (root-level, not under `/api`) |
| `/responses` | POST | No | Alias of `/invocations` |
| `/api/agents/chat` | POST | **SSE** | Streaming, HITL-capable — the chat UI surface |
| `/api/agents/approve` | POST | — | Approve/deny a pending destructive tool call (stream owner only → `403` otherwise) |
| `/api/agents/cancel` | POST | — | Cancel a stream; denies its pending approvals |

**No HITL on `/invocations` / `/responses`.** They are non-streaming, so with the default approval gate on, an agent that has any **mutating** tool (`effect: "write" | "update" | "destructive"`) is rejected there with HTTP **400** before running. Route HITL agents through `POST /api/agents/chat`, or disable the gate for autonomous back-office agents: `agents({ approval: { requireForDestructive: false } })`.

## Human-in-the-loop approval

Mutating tools require explicit approval by default (secure by default). Flow: the plugin emits an `appkit.approval_pending` SSE event → the client renders a prompt → the **same** user posts `{ streamId, approvalId, decision }` to `/api/agents/approve`. No decision within `approval.timeoutMs` (60 s) auto-denies. Built-in `analytics.query` is read-only-enforced (only `SELECT`/`WITH`/`SHOW`/`EXPLAIN`/`DESCRIBE` pass); `lakebase.query` is **off by default** and runs as the **service principal** — enable only with the explicit `exposeAsAgentTool` acknowledgement.

## Skills (agent runtime skills)

On-demand instruction packs in the same `SKILL.md` format Claude Code uses — only each skill's name + description sit in the prompt; the body loads when the agent (or the user, via `/skill-name`) invokes it. Per-agent skills live in `server/agents/<id>/skills/`; shared ones in `server/agents/skills/` (opt-in via frontmatter `skills:`) or a UC Volume (`DATABRICKS_VOLUME_AGENT_SKILLS`, read as the SP). v1 loads prose only — **scripts are not executed**, `allowed-tools` is advisory, and skill bodies are not per-user access-controlled. Details: `npx @databricks/appkit docs ./docs/plugins/agents.md`.

## Anti-patterns

| Mistake | Why it's wrong | What to do |
|---------|---------------|------------|
| `import { agents } from "@databricks/appkit"` | `agents` is beta — not in the main barrel | Import from `@databricks/appkit/beta` |
| Code agent works in dev, gone in prod | `agent.ts` not bundled — no build entry | Use `appkitServerConfig()` in `tsdown.server.config.ts` |
| Agent answers but never calls tools | Auto-inherit is off; no `tools:` declared | Declare `tools:` (frontmatter) or `tools(plugins)` (code); register the plugin in `createApp` |
| Referenced plugin not in `createApp({ plugins })` | Plugin throws at setup with `Available: …` | Add it to `--features` / the `plugins` array |
| Pointing an agent at a `pyfunc`/`sklearn` endpoint | Not streaming → `Response body is null` | Use a streaming chat endpoint, or `fromSupervisorApi` |
| Function tools / sub-agents on a Supervisor-API agent | Managed runtime ignores them (warning only) | Use `supervisorTools.*`, or switch to a serving-endpoint backend |
| Building chat UI by hand-rolling SSE | Extra bugs; misses thread/approval handling | Use the `useAgentChat` hook |
| Chat area collapses to zero height | No explicit height on the container | Give the parent a fixed height |
| Destructive-tool agent on `/invocations` | Non-streaming surface can't do HITL → 400 | Use `/api/agents/chat`, or disable the approval gate |

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|---------|
| `Response body is null — streaming not supported` | Serving endpoint doesn't stream | Point at a streaming chat endpoint, or use `DatabricksAdapter.fromSupervisorApi` |
| `400` from `/invocations` mentioning approval-gated tools | Non-streaming surface + mutating tool + gate on | Use `/api/agents/chat`, or `approval: { requireForDestructive: false }` |
| Code agent not discovered in a built server | Missing build entry for `server/agents/*/agent.ts` | Adopt `appkitServerConfig()` |
| Code agent edits ignored in dev | Stale `dist/agents` shadows source | Delete the build dir |
| Plugin throws `Available: …` at setup | Agent references an unregistered plugin's tools | Register the plugin in `createApp` / add to `--features` |
| `plugin "agents" has no resource with key "..."` | Wrong `--set` key at scaffold | Derive keys from `databricks apps manifest` |
| `403` from `/api/agents/approve` | Decider isn't the stream owner | The same `x-forwarded-user` that opened the stream must approve |

## Full API

Signatures, the config reference (`autoInheritTools`, `approval`, `limits`, `threadStore`, `mcp` host policy), the frontmatter schema, sub-agents, and the Supervisor API adapter live in the source-of-truth doc:

```bash
npx @databricks/appkit docs ./docs/plugins/agents.md
```
