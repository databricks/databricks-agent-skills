# Generating & Editing Images

Generate images from text, or edit a reference image, using Foundation Models on Databricks AI Gateway from a Node.js/AppKit app.

There are **two distinct APIs**. Each returns images in the same shape for generation and editing:

| Provider | Endpoint | Mechanism | Image location in response |
|----------|----------|-----------|----------------------------|
| **OpenAI** | `POST /serving-endpoints/responses` | Responses API with the built-in `image_generation` **tool** | `output[].image_generation_call.result` (base64) |
| **Gemini** | `POST /serving-endpoints/<endpoint>/invocations` | Chat completions; the model emits an image inline | `choices[0].message.content[].image_url.url` (data URL) |

Both are workspace-global `system.ai.*` pay-per-token endpoints. They do **not** need to be attached to the app as a resource, and OBO is not required. Calls run as the app's execution identity: the app service principal when deployed, your own credentials in local dev.

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

Smoke-test an endpoint before wiring it up (leave out `size`/`quality` for now):

```bash
# OpenAI Responses API
curl -s -X POST -H "Authorization: Bearer $DATABRICKS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"databricks-gpt-5","input":"a red bicycle","tools":[{"type":"image_generation"}]}' \
  "$DATABRICKS_HOST/serving-endpoints/responses" | jq '.output[].type'

# Gemini image model (chat completions)
curl -s -X POST -H "Authorization: Bearer $DATABRICKS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"a red bicycle"}]}' \
  "$DATABRICKS_HOST/serving-endpoints/databricks-gemini-3-1-flash-image/invocations" \
  | jq '.choices[0].message.content[0].type'
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
      "background": "transparent"  // transparent | opaque — omit for auto
    }
  ]
}
```

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
- **Iterative editing**: pass the previous result's `dataUrl` back in as the next reference image. Stored responses (`previous_response_id`) aren't supported, so resend the image every time.
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

Either `dataUrl` can go straight into `<img src={dataUrl}>`. To decode it server-side, use `Buffer.from(base64, 'base64')`.

## 5. Server route & authentication (the gotchas)

Call the endpoints from a custom Express route registered with `appkit.server.extend` inside `onPluginsReady` (see [Custom Endpoints](custom-endpoints.md)). Don't use the `serving()` plugin here: it's deprecated, and it targets chat/streaming rather than image output. Image payloads hit several limits that ordinary JSON calls don't:

**Gotcha A — don't use the top-level `getWorkspaceClient()` export.** In `@databricks/appkit`, that name is re-exported from the **Lakebase** connector, not from the execution context. Calling it with no args throws `Cannot read properties of undefined (reading 'workspaceClient')`. Use `getExecutionContext().client` instead.

**Gotcha B — don't use the SDK's `apiClient.request()` or `servingEndpoints.query()` for image calls.** The SDK's HTTP client times out after `httpTimeoutSeconds` (default **5s**). Image generations take 20–60s, so the request is aborted early and shows up as a misleading `502 Bad Gateway`. Get the host and auth headers from the SDK config and call the native `fetch`.

**Gotcha C — handle the 120s proxy timeout and non-JSON responses.** The Databricks Apps reverse proxy ends requests after **120s**, a limit you can't change (see [Platform Guide](../platform-guide.md)). When that happens it returns an **HTML** error page. Abort server-side just before the limit so the app returns clean JSON. On the client, read the body as text and parse it defensively; calling `res.json()` on HTML throws the cryptic `Unexpected token '<'`.

**Gotcha D — raise the body limit.** The server plugin's `express.json()` defaults to `bodyLimit: "1mb"`, which rejects reference images with `413`. Set `server({ bodyLimit: "25mb" })` and validate the input, e.g. `z.string().startsWith("data:image/").max(20_000_000)`.

```ts
// server/imageGeneration.ts
import { getExecutionContext } from '@databricks/appkit';

export async function callServing(path: string, payload: unknown): Promise<unknown> {
  const { client } = getExecutionContext();
  const config = client.config;
  await config.ensureResolved();
  const host = await config.getHost();              // works in local dev & deployed
  const headers = new Headers({ 'Content-Type': 'application/json' });
  await config.authenticate(headers);               // PAT/CLI auth locally, OAuth after deploy

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 115_000); // < 120s proxy timeout
  try {
    const res = await fetch(new URL(path, host).toString(), {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (!res.ok) {
      throw new Error(`Serving request failed (${res.status}): ${(await res.text()).slice(0, 400)}`);
    }
    return res.json();
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new Error('The model did not respond in time. Try a smaller size, lower quality, or a faster model.');
    }
    throw err;
  } finally {
    clearTimeout(timeout);
  }
}
```

```ts
// server/server.ts
import { createApp, server } from '@databricks/appkit';
import { z } from 'zod';
import { callServing } from './imageGeneration';

const GenerateRequest = z.object({
  prompt: z.string().min(1),
  image: z.string().startsWith('data:image/').max(20_000_000).optional(),
});

await createApp({
  plugins: [server({ bodyLimit: '25mb' })],
  onPluginsReady(appkit) {
    appkit.server.extend((app) => {
      app.post('/api/generate-image', async (req, res) => {
        // Express 4 does not forward rejected promises — catch here
        try {
          const input = GenerateRequest.parse(req.body);
          // build the OpenAI or Gemini payload (sections 2–3), then:
          // const result = await callServing('/serving-endpoints/responses', payload);
          // extract the dataUrl (section 4) and return it
          res.json({ dataUrl: '…' });
        } catch (err) {
          res.status(500).json({ error: err instanceof Error ? err.message : String(err) });
        }
      });
    });
  },
});
```

Narrow the `unknown` JSON response with runtime checks (`typeof x === 'object' && x !== null`) rather than `as` casts, because `appkit lint` forbids double type assertions.

If you echo the request payload back to the UI (useful for showing users exactly what was sent), deep-clone it first and replace long `data:image…` strings with a short placeholder. Otherwise the preview fills with megabytes of base64.

## 6. Operational notes

- **Latency**: Gemini image models take about 5–20s. OpenAI GPT-5 with reasoning can take 30–60s, and edits of large references take longer. Leave `size`/`quality` on auto and downscale references to stay under the 120s limit. For batches, generate one image per request.
- **Access**: the app service principal can query `system.ai.*` pay-per-token endpoints by default. A `403` after deploy means either the endpoint isn't a system Foundation Model endpoint or the SP was denied access. Fix the grant; don't fall back to a hard-coded token.
- **Gemini image models** run on a global endpoint, so **cross-geography routing** must be enabled in the workspace. They are pay-per-token only (no provisioned throughput, `ai_query`, or AI Playground), and output image tokens are billed separately from text tokens.
- **Payload size**: base64 PNGs are large (a 1024×1024 image is about 1.5–2 MB). Returning a data URL from the app's own `/api` route is fine, but don't log the full body.

## References

- [Query with the OpenAI Responses API](https://docs.databricks.com/aws/en/machine-learning/model-serving/query-openai-responses): `/serving-endpoints/responses`, supported models and tools (`image_generation`), unsupported parameters
- [Foundation Model REST API reference](https://docs.databricks.com/aws/en/machine-learning/foundation-model-apis/api-reference): chat completions and Responses request/response schemas
- [Supported Foundation Models](https://docs.databricks.com/aws/en/machine-learning/foundation-model-apis/supported-models): Gemini `-image` endpoints and their limitations
- [Databricks Apps best practices](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/best-practices): async + polling for long-running operations
- [Platform Guide](../platform-guide.md): 120s proxy timeout and other platform limits
- AppKit docs: `npx @databricks/appkit docs ./docs/plugins/server.md` (custom routes, `server()` config) and `./docs/plugins/execution-context.md` (`getExecutionContext`, service principal vs OBO)
