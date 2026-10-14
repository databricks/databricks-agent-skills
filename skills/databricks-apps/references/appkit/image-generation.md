# Generating & Editing Images

Generate images from text, or edit a reference image, using Foundation Models on Databricks AI Gateway from a Node.js/AppKit app.

There are **two distinct APIs**. Each returns images in the same shape for generation and editing:

| Provider | Endpoint | Mechanism | Image location in response |
|----------|----------|-----------|----------------------------|
| **OpenAI** | `POST /serving-endpoints/responses` | Responses API with the built-in `image_generation` **tool** | `output[].image_generation_call.result` (base64) |
| **Gemini** | `POST /serving-endpoints/<endpoint>/invocations` | Chat completions; the model emits an image inline | `choices[0].message.content[].image_url.url` (data URL) |

Both are workspace-global `system.ai.*` pay-per-token endpoints. They do **not** need to be attached to the app as a resource, and OBO is not required. Calls run as the app's execution identity: the app service principal when deployed, your own credentials in local dev. Section 5 shows how to call them from an AppKit app.

## 1. Discover image-capable endpoints

Model names change often. Check what's live before hard-coding anything:

```bash
databricks serving-endpoints list --profile <PROFILE> \
  | jq -r '.[]
      | select(.name | startswith("databricks-"))
      | select((.config.served_entities[0].entity_name // "") | startswith("system.ai."))
      | "\(.task)\t\(.name)"' \
  | sort
```

- **OpenAI**: use a GPT model endpoint such as `databricks-gpt-5`. The model calls the Responses `image_generation` tool itself, so there is no separate "image endpoint". The same endpoint both generates and edits.
- **Gemini**: use an endpoint whose name ends in `-image`, e.g. `databricks-gemini-3-pro-image` (highest fidelity) or `databricks-gemini-3-1-flash-image` (faster). These have `task: llm/v1/chat`, and they both generate and edit. Non-`-image` Gemini chat models do not return images.

Smoke-test an endpoint before wiring it up. GPT-5 image calls often run past the CLI's 60s inactivity timeout, so call the Responses API with `curl` and a CLI-issued token. `output_format: "jpeg"` keeps the response under the size limit (see section 2):

```bash
# OpenAI Responses API
HOST=$(databricks auth describe --profile <PROFILE> -o json | jq -r .details.host)
TOKEN=$(databricks auth token --profile <PROFILE> | jq -r .access_token)
curl -s --max-time 300 "$HOST/serving-endpoints/responses" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"model":"databricks-gpt-5","input":"a red bicycle","tools":[{"type":"image_generation","quality":"low","output_format":"jpeg"}]}' \
  | jq -r '.output[].type'

# Gemini image model (chat completions)
databricks api post /serving-endpoints/databricks-gemini-3-1-flash-image/invocations --profile <PROFILE> \
  --json '{"messages":[{"role":"user","content":"a red bicycle"}]}' \
  | jq -r '.choices[0].message.content[].type'
```

The OpenAI call should list an `image_generation_call` item. The Gemini call should print `image_url`.

## 2. Generate from a text prompt

**OpenAI — Responses API.** Unlike chat completions, the request uses `input` (a string or structured input) instead of `messages`, and `image_generation` is passed as a **tool**. Tool-level options tune the image:

```jsonc
{
  "model": "databricks-gpt-5",
  "input": "A serene mountain lake at sunrise, mist over the water",
  "tools": [
    {
      "type": "image_generation",
      "size": "1024x1024",        // or 1536x1024, 1024x1536 — omit for auto
      "quality": "low",            // low | medium | high — omit for auto
      "output_format": "jpeg",     // png (default) | jpeg | webp — see below
      "background": "opaque"       // transparent (png/webp only) | opaque — omit for auto
    }
  ]
}
```

⚠️ **Set `output_format` to `jpeg` or `webp`.** The default PNG at `medium`/`high` quality makes the response larger than the 4,000,000-byte serving limit, and the call fails with `400 MAX_READ_SIZE_EXCEEDED`. Measured on GPT-5, JPEG and WebP results are about 0.4–0.55 MB at any quality. Only `quality: "low"` PNGs fit.

⚠️ Don't confuse the tool's `background` field with the **top-level** Responses `background` parameter. On pay-per-token endpoints, top-level `background`, `store`, and `previous_response_id` return `400`.

**Gemini — chat completions.** Send the prompt as a user message. The image comes back inline, and no tool is needed.

```jsonc
{ "messages": [{ "role": "user", "content": "A serene mountain lake at sunrise" }] }
```

## 3. Edit an existing image (image-to-image)

To edit, send the reference image **alongside** the prompt as a structured content part. A base64 **data URL** works directly, so there's no upload step. The response shape is the same as for generation, so extract the result as in section 4. The prompt becomes the edit instruction ("add a hat", "make it winter", "remove the background").

**OpenAI**: `input` becomes a structured message with an `input_image` part. Keep the `image_generation` tool and its options:

```jsonc
{
  "model": "databricks-gpt-5",
  "input": [{ "role": "user", "content": [
    { "type": "input_text",  "text": "Add a bright red party hat." },
    { "type": "input_image", "image_url": "data:image/jpeg;base64,…" }
  ]}],
  "tools": [{ "type": "image_generation" }]
}
```

**Gemini**: the message `content` becomes an array with an `image_url` part:

```jsonc
{ "messages": [{ "role": "user", "content": [
  { "type": "text",      "text": "Add a bright red party hat." },
  { "type": "image_url", "image_url": { "url": "data:image/jpeg;base64,…" } }
]}]}
```

- **No separate edit endpoint**: GPT-5 (via the tool) and the Gemini `-image` models both edit natively.
- **Multiple references**: add more `input_image` / `image_url` parts to combine images or transfer style between them.
- **Iterative editing**: pass the previous result back in as the next reference image. Stored responses (`previous_response_id`) aren't supported, so resend the image every time.
- **Downscale references client-side** before sending (e.g. draw onto a canvas with a max edge of ~1536px and export JPEG). Raw photos are several megabytes, and base64 adds about 33%.

## 4. Response shapes & extraction

**OpenAI.** `output` is an array that mixes `reasoning`, `message`, and `image_generation_call` items. Take the image from the call item:

```ts
// item.type === "image_generation_call"
const dataUrl = `data:image/${item.output_format ?? 'png'};base64,${item.result}`;
const revisedPrompt = item.revised_prompt; // the model's rewritten prompt
```

**Gemini.** `choices[0].message.content` is an array of parts. Find the image part:

```ts
// part.type === "image_url"
const dataUrl = part.image_url.url; // already "data:image/png;base64,..."
```

To decode either `dataUrl` server-side, use `Buffer.from(base64, 'base64')`. The `dataUrl` also works directly as `<img src>`.

**Handle "no image" responses.** A response can succeed (HTTP 200) and still contain no image, for example when the model refuses the prompt or asks a clarifying question. For Gemini, `content` is then a plain string or holds only `text` parts. For OpenAI, there's no `image_generation_call` item, only a `message`. Collect the text and return it as a user-facing error rather than "unexpected response".

## 5. Wire it into AppKit

Pick the path by UI:

| UI | Path |
|----|------|
| Button or form: one prompt, one image | **[5a. Streaming route](#5a-streaming-route-default)** (default) |
| Chat with conversational edits ("now make it stormy") | **[5b. Agent tool](#5b-agent-tool-chat-uis)** on the `agents` plugin |

Don't use the deprecated `serving()` plugin. It targets chat/streaming, not image output.

**Why stream: the Apps proxy limits.** Measured on E2 Dogfood with an app that sleeps before responding:

| | Plain JSON response | Streamed response (headers first, heartbeat every 10s) |
|--|--|--|
| Container (classic) app | OK up to 300s, then `504` | OK up to 300s, then the stream is cut |
| Spaces app (behind the Apps gateway) | **`502` HTML page at 60s** | OK up to 300s, then the stream is cut |

GPT-5 image calls take 25–110s, sometimes longer, so a plain JSON route fails on Spaces apps, and on any app the gateway fronts later. Send headers immediately and keep bytes flowing, and the same code works on both app types. Hard cap: **5 minutes**.

### Shared server helper

```ts
// server/imageGeneration.ts
import { getExecutionContext } from '@databricks/appkit';
import { z } from 'zod';

async function callServing(path: string, payload: unknown): Promise<unknown> {
  const { client } = getExecutionContext();
  const config = client.config;
  await config.ensureResolved();
  const host = await config.getHost();              // works in local dev & deployed
  const headers = new Headers({ 'Content-Type': 'application/json' });
  await config.authenticate(headers);               // PAT/CLI auth locally, OAuth after deploy

  const res = await fetch(new URL(path, host).toString(), {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(280_000),           // just under the 5-minute proxy cap
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`Serving request failed (${res.status}): ${text.slice(0, 400)}`);
  return JSON.parse(text);
}

const ImageGenerationResponse = z.object({
  output: z.array(z.object({ type: z.string(), result: z.string().optional(), output_format: z.string().optional() }).loose()),
});

/** Generates an image, or edits one when given a reference, and returns it as a data URL. */
export async function generateImage(prompt: string, referenceDataUrl?: string): Promise<string> {
  const input = referenceDataUrl
    ? [{ role: 'user', content: [
        { type: 'input_text', text: prompt },
        { type: 'input_image', image_url: referenceDataUrl },
      ] }]
    : prompt;
  const body = ImageGenerationResponse.parse(
    await callServing('/serving-endpoints/responses', {
      model: 'databricks-gpt-5',
      input,
      tools: [{ type: 'image_generation', output_format: 'jpeg' }], // PNG can exceed the 4 MB response limit
    }),
  );
  const call = body.output.find((o) => o.type === 'image_generation_call' && o.result);
  if (!call?.result) throw new Error('The model returned no image. Rephrase the prompt.');
  return `data:image/${call.output_format ?? 'jpeg'};base64,${call.result}`;
}
```

For Gemini, swap the payload for chat completions (sections 2–3) and read the image part of `choices[0].message.content` (section 4). If there's no image part, throw the model's text.

### 5a. Streaming route (default)

The route sends headers right away, writes a blank line every 10s, then writes one JSON result line. Once headers are out the status is always `200`, so errors travel in the body as `{ error }`.

```ts
// server/server.ts
import { createApp, server } from '@databricks/appkit';
import type { Response } from 'express';
import { z } from 'zod';
import { generateImage } from './imageGeneration';

const GenerateRequest = z.object({
  prompt: z.string().min(1),
  image: z.string().startsWith('data:image/').max(20_000_000).optional(), // reference image for edits
});

// Streams one NDJSON result line; blank-line heartbeats keep the proxies from timing out
async function streamResult(res: Response, work: () => Promise<unknown>) {
  res.setHeader('Content-Type', 'application/x-ndjson');
  res.flushHeaders();
  const heartbeat = setInterval(() => res.write('\n'), 10_000);
  try {
    res.end(JSON.stringify(await work()) + '\n');
  } catch (err) {
    res.end(JSON.stringify({ error: err instanceof Error ? err.message : String(err) }) + '\n');
  } finally {
    clearInterval(heartbeat);
  }
}

await createApp({
  plugins: [server({ bodyLimit: '25mb' })], // default 1mb rejects reference images with 413
  onPluginsReady(appkit) {
    appkit.server.extend((app) => {
      app.post('/api/generate-image', (req, res) => {
        const parsed = GenerateRequest.safeParse(req.body);
        if (!parsed.success) return res.status(400).json({ error: parsed.error.message });
        void streamResult(res, async () => ({ dataUrl: await generateImage(parsed.data.prompt, parsed.data.image) }));
      });
    });
  },
});
```

```ts
// client/src/generateImage.ts
import { z } from 'zod';

const GenerateResult = z.union([z.object({ dataUrl: z.string() }), z.object({ error: z.string() })]);

export async function generateImage(prompt: string, image?: string): Promise<string> {
  const res = await fetch('/api/generate-image', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, image }),
  });
  // NDJSON: blank heartbeat lines, then one result line. Errors before streaming starts are plain JSON or an HTML proxy page.
  const text = await res.text();
  let parsed: unknown;
  try { parsed = JSON.parse(text.trim().split('\n').pop() ?? ''); } catch { throw new Error(`Unexpected response (${res.status})`); }
  const result = GenerateResult.parse(parsed);
  if ('error' in result) throw new Error(result.error);
  return result.dataUrl;
}
```

The returned `dataUrl` goes straight into `<img src={dataUrl}>`. To edit, pass the previous `dataUrl`, or a downscaled upload, back as `image`.

### 5b. Agent tool (chat UIs)

For a chat UI, make image generation a tool on an [`agents`](agents.md) agent. A chat LLM decides when to generate or edit, and the `/api/agents/chat` SSE stream already sends heartbeats. Read [Agents](agents.md) first: `agents` is imported from `@databricks/appkit/beta`, and code agents need `appkitServerConfig()` in the build.

Weigh the cost before choosing this. Every request adds two chat-LLM turns, which means extra seconds and tokens. The LLM also rewrites prompts and may retry failed generations on its own, and each retry is billed.

Tool results are JSON-serialized into the LLM context, capped at 50k characters, so the tool stores the image and returns an `imageId`:

```ts
// server/imageStore.ts
import { randomUUID } from 'node:crypto';

// In-memory: lost on restart and not shared across replicas. Persist to a UC Volume if images must outlive the process.
const MAX_IMAGES = 200;
const images = new Map<string, { mime: string; bytes: Buffer }>();

export function putImage(dataUrl: string): string {
  const match = /^data:(image\/[\w+.-]+);base64,(.+)$/s.exec(dataUrl);
  if (!match) throw new Error('Expected a base64 image data URL');
  const id = randomUUID(); // unguessable: the id is the only access check on GET /api/images/:id
  images.set(id, { mime: match[1], bytes: Buffer.from(match[2], 'base64') });
  if (images.size > MAX_IMAGES) images.delete(images.keys().next().value!);
  return id;
}

export const getImage = (id: string) => images.get(id);

export function imageDataUrl(id: string): string {
  const img = images.get(id);
  if (!img) throw new Error(`Unknown imageId ${id}`);
  return `data:${img.mime};base64,${img.bytes.toString('base64')}`;
}
```

```ts
// server/agents/artist/agent.ts — agent id = folder name
import { createAgent, tool } from '@databricks/appkit/beta';
import { z } from 'zod';
import { generateImage } from '../../imageGeneration';
import { imageDataUrl, putImage } from '../../imageStore';

export default createAgent({
  instructions:
    'You create and edit images. Call generate_image for every image request. ' +
    'To edit, pass the imageId of the image to change as referenceImageId. ' +
    'The UI shows the image. Reply with one short sentence that ends with "(imageId: <id>)" for each image you made, ' +
    'so later turns can edit it: tool results are not kept in the conversation history.',
  model: 'databricks-claude-sonnet-4-5', // the chat LLM; any streaming chat endpoint
  tools: {
    generate_image: tool({
      description:
        'Generate an image from a text prompt, or edit an existing image when referenceImageId is given. ' +
        'Returns { imageId } for the new image.',
      schema: z.object({
        prompt: z.string().min(1).describe('What to draw, or the edit instruction'),
        referenceImageId: z.string().uuid().optional().describe('imageId of an earlier or uploaded image to edit'),
      }),
      async execute({ prompt, referenceImageId }) {
        const reference = referenceImageId ? imageDataUrl(referenceImageId) : undefined;
        return { imageId: putImage(await generateImage(prompt, reference)) };
      },
    }),
  },
});
```

Register `agents()` next to `server()`, and add routes that serve images and accept reference uploads:

```ts
// server/server.ts — additions for the agent path
import { agents } from '@databricks/appkit/beta';
import { getImage, putImage } from './imageStore';

const UploadRequest = z.object({ image: z.string().startsWith('data:image/').max(20_000_000) });

// plugins: [server({ bodyLimit: '25mb' }), agents()],
// inside appkit.server.extend((app) => { ... }):
app.get('/api/images/:id', (req, res) => {
  const img = getImage(req.params.id);
  if (!img) return res.status(404).end();
  res.type(img.mime).send(img.bytes);
});
// Reference images for edits: upload once, then mention the returned imageId in the chat
app.post('/api/images', (req, res) => {
  const parsed = UploadRequest.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: parsed.error.message });
  res.json({ imageId: putImage(parsed.data.image) });
});
```

On the client, `useAgentChat` streams the assistant text. Tool results arrive through `onEvent` as `response.output_item.done` items with `item.type === "function_call_output"`; `item.output` is the tool's JSON-serialized return value:

```tsx
import { useState } from 'react';
import { useAgentChat } from '@databricks/appkit-ui/react';
import { z } from 'zod';

const ImageToolOutput = z.object({ imageId: z.string() });

export function ImageChat() {
  const [imageIds, setImageIds] = useState<string[]>([]);
  const { content, isStreaming, error, send } = useAgentChat({
    agent: 'artist',
    onEvent(ev) {
      if (ev.type !== 'response.output_item.done' || ev.item?.type !== 'function_call_output') return;
      let output: unknown;
      try { output = JSON.parse(ev.item.output ?? ''); } catch { return; } // tool errors are plain strings
      const parsed = ImageToolOutput.safeParse(output);
      if (parsed.success) setImageIds((ids) => [...ids, parsed.data.imageId]);
    },
  });
  // Edit an upload: POST { image: dataUrl } to /api/images, then send(`Edit image ${imageId}: ${instruction}`)
  return (
    <div>
      {imageIds.map((id) => <img key={id} src={`/api/images/${id}`} alt="" />)}
      <p>{content}</p>
      {error && <p role="alert">{error}</p>}
      <button disabled={isStreaming} onClick={() => send('A lighthouse at dusk, watercolor')}>Generate</button>
    </div>
  );
}
```

Agent-path specifics:
- **Identity.** By default, a hand-rolled `tool({ execute })` runs as the app service principal. With `auth: "on-behalf-of-user"`, `getExecutionContext()` inside the tool resolves to the user, and the app then needs the `model-serving` user API scope.
- **Match AppKit's `zod`.** `tool({ schema })` fails to type-check (`_zod.version.minor`) if the app's `zod` differs from AppKit's.
- **Approval.** The tool has no `effect` annotation, so it runs without an approval prompt. Add `annotations: { effect: "write" }` to make users confirm each billed generation.

### Gotchas (both paths)

- **Don't use the top-level `getWorkspaceClient()` export.** In `@databricks/appkit`, that name is re-exported from the **Lakebase** connector. Calling it with no args throws `Cannot read properties of undefined (reading 'workspaceClient')`. Use `getExecutionContext().client`.
- **Don't use the SDK's `apiClient.request()` or `servingEndpoints.query()`.** The SDK HTTP client times out after `httpTimeoutSeconds` (default **5s**), and that surfaces as a misleading `502`. Use native `fetch` with the SDK config's host and auth headers, as `callServing` does.
- **Narrow responses with zod, not `as` casts.** `appkit lint` forbids double type assertions.
- **Don't echo payloads raw.** Before showing a request in the UI or a log, replace long `data:image…` strings with a placeholder.

## 6. Operational notes

- **Latency**: Gemini image models take about 5–30s. OpenAI GPT-5 varies widely: about 25–110s even on `quality: "low"`, longer on `high` or with large references. Budget minutes, not seconds, and stay under the 5-minute proxy cap (section 5). In the agent path, the chat LLM's own turns add a few seconds. Downscale references before upload, and generate one image per tool call.
- **Access**: the app service principal can query `system.ai.*` pay-per-token endpoints by default. A `403` after deploy means either the endpoint isn't a system Foundation Model endpoint or the SP was denied access. Fix the grant; don't fall back to a hard-coded token.
- **Gemini image models** run on a global endpoint, so **cross-geography routing** must be enabled in the workspace. They are pay-per-token only (no provisioned throughput, `ai_query`, or AI Playground), and output image tokens are billed separately from text tokens.
- **Payload size**: base64 PNGs are large (a 1024×1024 image is about 1.5–2 MB). Don't log them, and in the agent path pass `imageId`s instead.

## References

- [Query with the OpenAI Responses API](https://docs.databricks.com/aws/en/machine-learning/model-serving/query-openai-responses): `/serving-endpoints/responses`, supported models and tools (`image_generation`), unsupported parameters
- [Foundation Model REST API reference](https://docs.databricks.com/aws/en/machine-learning/foundation-model-apis/api-reference): chat completions and Responses request/response schemas
- [Supported Foundation Models](https://docs.databricks.com/aws/en/machine-learning/foundation-model-apis/supported-models): Gemini `-image` endpoints and their limitations
- [Agents](agents.md): `agents()` plugin setup, code agents, `useAgentChat` (path 5b)
- AppKit docs: `npx @databricks/appkit docs ./docs/plugins/agents.md` (function tools, `auth` modes, SSE events), `./docs/plugins/server.md` (custom routes, `server()` config), and `./docs/plugins/execution-context.md` (`getExecutionContext`)
