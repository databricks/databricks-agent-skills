# agent-browser: Render a Running App for Visual Inspection

Use this when you (or an agent) need to **load a Databricks app in a browser and interact with it programmatically** — verify a UI change, capture a screenshot, drive a smoke flow.

The primary target is a **deployed app URL** (real OAuth/SSO). For local UI iteration, the right path is the app's own Vite dev server (`npm run dev`) — no platform proxy, no auth, instant HMR. The `databricks apps run-local` proxy is an edge case for testing platform header-injection behavior locally without deploying; covered at the bottom.

| | **Deployed app** (primary) | **Local Vite dev server** | **Local platform proxy** (edge case) |
|---|---|---|---|
| When | Verify what's actually in staging/prod | Iterate on UI code with HMR | Test how the app behaves under the platform's auth-header proxy without deploying |
| Auth | Real OAuth/SSO | None | None — proxy injects fake `X-Forwarded-*` |
| Run command | (already deployed) | `npm run dev` | `databricks apps run-local --entry-point app.yaml` |
| agent-browser command | `agent-browser --headed --profile <dir> open <url>` (first run); plain `agent-browser open <url>` after | `agent-browser open http://localhost:<vite-port>` | `agent-browser open http://localhost:8001` |

The browser daemon persists across commands; only the auth path differs.

## When NOT to use this

- **Non-visual smoke tests** — for AppKit, the scaffold ships `tests/smoke.spec.ts` (Playwright); see [testing.md](../testing.md).
- **Verifying real per-user OBO behavior** — only the deployed app gives you a real OBO token. Neither Vite nor `run-local` will.

## Pre-flight checks

Run these before anything else. If any fail, surface the failing check and stop — don't try to fix forward.

1. **`agent-browser` on PATH** — `command -v agent-browser`. If missing, install it (it's a public npm package):
   ```bash
   npm install -g agent-browser
   # or: pnpm add -g agent-browser
   # or: yarn global add agent-browser
   ```
   Then re-check with `command -v agent-browser` and `agent-browser --version`. Surface the failing check to the user before continuing — don't try to script around a missing binary.
2. **(Deployed mode)** the user can navigate to the deployed app URL in a regular browser and log in via SSO — that is the login `--headed --profile` will reproduce once.
3. **(Deployed mode, if discovering the URL)** `databricks` on PATH and authenticated for the workspace — `databricks apps list --profile <PROFILE>`.

## Driving a deployed app (primary)

For URLs like `https://<name>.<workspace>.databricksapps.com`, the platform demands real OAuth/SSO. Pick one of the following.

### Preferred: `--headed --profile <dir>` (one-time SSO)

```bash
# First run — interactive: user logs in via SSO once; cookies persist in <dir>:
agent-browser --headed --profile ./.agent-browser-profile open <deployed-url>

# Subsequent runs — same profile, no login prompt:
agent-browser --profile ./.agent-browser-profile open <deployed-url>
```

Use this by default. Least disruptive — it doesn't touch the user's regular Chrome.

### Alternative: `--auto-connect` to an existing Chrome

Only viable if Chrome is **already** running with `--remote-debugging-port=9222`. A normal Chrome window does **not** have this flag, and you cannot add it to a running Chrome — relaunching the binary with the flag prints `Opening in existing browser session` and silently no-ops.

To use this path:

```bash
# Fully quit Chrome first (closing the window is not enough):
osascript -e 'quit app "Google Chrome"'

# Relaunch with the debug port:
open -a "Google Chrome" --args --remote-debugging-port=9222

# Then connect:
agent-browser --auto-connect open <deployed-url>
```

Disruptive if the user has working tabs. Only suggest this if `--headed --profile` won't work.

### Sharing a logged-in session across runs / CI

Use `agent-browser state save` after a successful login and `agent-browser state load` in subsequent runs. Run `agent-browser skills get core` for the full auth-vault surface.

## Driving with agent-browser

Once a session is open, the browser persists across commands:

```bash
agent-browser snapshot -i              # see interactive elements as @e1, @e2, ...
agent-browser screenshot home.png      # capture for inspection
# ... interact with refs from the snapshot ...
agent-browser close
```

For the full agent-browser surface (refs, waits, find-by-role, auth vault), run `agent-browser skills get core`.

**Daemon flag-ignore gotcha**: when the agent-browser daemon is already running, `--headed` and `--profile` on a subsequent invocation are silently ignored:

```
⚠ --profile, --headed ignored: daemon already running.
   Use 'agent-browser close' first to restart with new options.
```

Always run `agent-browser close` before changing launch flags.

## Driving a local Vite dev server

For UI iteration, run the app's own dev server and point agent-browser at it:

```bash
# In the app directory:
npm run dev

# In another shell, once Vite prints "Local: http://localhost:<port>/":
agent-browser open http://localhost:<port>
```

No auth. No proxy. Just Vite (and, for AppKit, the backing tRPC server). This is the right path when you're iterating on UI code and don't need real platform auth, `X-Forwarded-*` headers, or OBO tokens. The exact port comes from Vite's startup output — don't hardcode it.

## Edge case: testing platform proxy behavior locally (`databricks apps run-local`)

Use this **only** when you need to verify how the app behaves under the deployed platform's auth-header proxy without actually deploying — e.g. checking that the app correctly reads `X-Forwarded-*`, behaves under prod-style service-principal-only execution, or is served the way the runtime serves it.

It is **not** the right tool for normal UI iteration (use `npm run dev`) and it is **not** the right tool for full deployed-app verification (use the real deployed URL).

### What the proxy does

`run-local` starts an HTTP proxy on `localhost:<port>` (default 8001) in front of the app (default `localhost:8000`). On every forwarded request it injects:

| Header | Value |
|---|---|
| `X-Forwarded-Host` | `localhost` |
| `X-Forwarded-User` | CLI user's `userName` |
| `X-Forwarded-Email` | CLI user's primary email (or `userName` if none) |
| `X-Forwarded-Preferred-Username` | CLI user's `displayName` |
| `X-Real-Ip` | `127.0.0.1` |
| `X-Request-Id` | fresh UUID per request |

These match the headers the Apps platform's auth proxy sets in production, so AppKit (and any framework that reads `X-Forwarded-*`) treats the request as authenticated. Identity comes from `WorkspaceClient.CurrentUser.Me()` for the active profile.

The proxy injects identity headers but **not** an OBO user token. Plugins or app code requiring an OBO token (anything calling `.asUser(req)` or reading a `user_api_scopes` token) will fail under `run-local` — drive the deployed app instead.

### Pre-flight (run-local only)

1. **App spec present** — `app.yaml` (AppKit) or `app.yml` in the working directory, OR pass `--entry-point <file>`.
2. **Proxy port free** — default 8001. If `lsof -i :8001` shows anything, pick a free port and pass `--port <n>`.

### Running

```bash
# AppKit apps use app.yaml:
databricks apps run-local --entry-point app.yaml --profile <PROFILE>

# First-time, if Python deps aren't installed (requires `uv`; Node-only apps just need `npm install`):
databricks apps run-local --prepare-environment --entry-point app.yaml --profile <PROFILE>

# Custom ports:
databricks apps run-local --port 8001 --app-port 8000 --entry-point app.yaml --profile <PROFILE>
```

If `app.yaml` declares env vars with `valueFrom` (referencing bundle resources like SQL warehouse IDs or Genie space IDs), `run-local` will exit with `... defined in app.yaml with valueFrom property and can't be resolved locally`. Pass each as `--env KEY=value`; values come from `databricks.yml` `targets.<target>.variables`.

`run-local` runs in the foreground and prints `To access your app go to http://localhost:<port>` once the proxy is listening. Run it in the background (or a separate shell), wait for the proxy to be reachable, then drive it:

```bash
until curl -fsS "http://localhost:8001/" -o /dev/null; do sleep 1; done
agent-browser open http://localhost:8001
```

### Two-port summary (don't mix these up)

- **`--port` (default 8001)** — the **proxy**. This is the URL you give to `agent-browser` and the URL printed by `run-local`. All traffic here gets the `X-Forwarded-*` headers.
- **`--app-port` (default 8000)** — the **app's own bind port**. The proxy forwards to this. Hitting it directly skips auth header injection — usually not what you want.

### Shutdown

Send SIGINT (Ctrl+C) to `run-local`. It forwards SIGTERM to the app and waits up to **15 seconds** before SIGKILL — same grace window the Apps platform uses, so handlers behave the same locally and in prod. Then `agent-browser close` to terminate the daemon.

## Gotchas

| Symptom | Cause | Fix |
|---|---|---|
| Deployed mode: `No running Chrome instance found. Launch Chrome with --remote-debugging-port` | A regular Chrome window has no debug port. Relaunching Chrome with the flag while it's already running just opens a new tab in the existing instance (`Opening in existing browser session`) — it does NOT add the flag | Fully quit Chrome (`osascript -e 'quit app "Google Chrome"'`), then `open -a "Google Chrome" --args --remote-debugging-port=9222`. Or simpler: switch to `--headed --profile`. |
| `⚠ --profile, --headed ignored: daemon already running` | A previous agent-browser run left the daemon up | `agent-browser close` first, then re-open with the desired flags. |
| Deployed mode: SSO login loop in `--headed` | Profile dir was reused after a credential rotation, or the workspace requires a fresh device check | Delete the profile dir and re-run with `--headed` to re-login from scratch. |
| `run-local` exits with `... defined in app.yaml with valueFrom property and can't be resolved locally` | `app.yaml` references bundle resources (warehouse, Genie space) that don't resolve outside a deployed bundle | Pass each `valueFrom` env var as `--env KEY=value`; values live in `databricks.yml` under `targets.<target>.variables`. |
| `run-local`: `app.yaml` not found / spec not picked up | AppKit scaffolds use `app.yaml`; older defaults look for `app.yml` | Pass `--entry-point app.yaml`. |
| `run-local`: AppKit app crashes with `AuthenticationError: Missing user token in request headers` | Proxy injects `X-Forwarded-*` identity but no OBO token; plugins requiring a user token reject this | Run `npm run dev` for UI iteration, or drive the **deployed** app for OBO behavior. The local proxy can't synthesize an OBO token. |
| `run-local`: app redirects to OAuth instead of loading | Framework isn't honoring `X-Forwarded-*`, or you bypassed the proxy and hit `--app-port` directly | Hit the **proxy** port (`--port`, default 8001), not the app port (`--app-port`, default 8000). |
| `run-local`: `address already in use` on start | Default port 8001 (or 8000) is taken | Pass `--port` and/or `--app-port` to free values. |
| `run-local`: app keeps running after Ctrl+C | App ignored SIGTERM | Wait 15s — `run-local` escalates to SIGKILL. Fix the handler in the app. |
| `run-local`: wrong user identity in the app | `databricks` is using a different profile than expected | Pass `--profile <PROFILE>` to `run-local`; verify with `databricks current-user me --profile <PROFILE>`. |
| `run-local`: `prepare-environment` fails | `uv` not installed | Install `uv`, or skip the flag and prepare deps yourself. For Node-only apps `npm install` is enough. |
