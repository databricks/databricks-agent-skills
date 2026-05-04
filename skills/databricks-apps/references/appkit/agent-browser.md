# agent-browser: Render a Running App for Visual Inspection

Use this when you (or an agent) need to **load a Databricks app in a browser and interact with it programmatically** — to verify a UI change, capture a screenshot, or drive a smoke flow.

There are two modes. Pick the right one before scripting:

| | **Local app** | **Deployed app** |
|---|---|---|
| What you're driving | `databricks apps run-local` on `localhost:<port>` | A real `https://<name>.<workspace>.databricksapps.com` URL |
| Auth | None — proxy injects `X-Forwarded-*` identity | Real OAuth/SSO required |
| Default command | `agent-browser open http://localhost:8001` | `agent-browser --headed --profile <dir> open <url>` (first run); plain `agent-browser open <url>` after |
| When | Iterating on the app from a checkout | Verifying what's actually deployed in staging/prod |

The browser daemon persists across commands either way; the only thing that changes is how the session is authenticated.

## When NOT to use this

- **Iterating on AppKit UI code** (HMR, fast reload) — use `npm run dev` from the app directory instead. `run-local` runs the app the way the platform runs it, not the way Vite does.
- **Verifying real per-user OBO behavior on local** — the injected identity is the CLI-authenticated user, not a per-session user. Fine for visualization, not for OBO permission testing. For OBO, drive the deployed app instead.
- **Non-visual smoke tests** — for AppKit apps the scaffold ships `tests/smoke.spec.ts` (Playwright); see [testing.md](../testing.md).

## Pre-flight checks

Run these before anything else. If any fail, surface the failing check and stop — don't try to fix forward.

1. **`databricks` on PATH and authenticated** — `databricks current-user me --profile <PROFILE>` should print a user. If not, run `databricks auth login --host <workspace-url>` and stop.
2. **`agent-browser` on PATH** — `command -v agent-browser`. If missing, install per the team's instructions and stop.
3. **(Local mode only) App spec present** — `app.yaml` (AppKit scaffolds) or `app.yml` in the working directory, OR pass `--entry-point <file>`. If neither, ask the user which directory the app lives in.
4. **(Local mode only) Proxy port free** — default is 8001. If `lsof -i :8001` shows anything, pick a free port and pass `--port <n>`. Remember that port when invoking agent-browser.

## Driving a local app (`run-local` proxy)

From the app directory:

```bash
# First run, when deps aren't installed (requires `uv`; for Node-only apps `npm install` is enough — skip the flag):
databricks apps run-local --prepare-environment --profile <PROFILE>

# Subsequent runs:
databricks apps run-local --profile <PROFILE>

# AppKit apps use app.yaml (not app.yml):
databricks apps run-local --entry-point app.yaml --profile <PROFILE>

# Custom ports:
databricks apps run-local --port 8001 --app-port 8000 --entry-point app.yaml --profile <PROFILE>
```

`run-local` runs in the foreground and prints `To access your app go to http://localhost:<port>` once the proxy is listening. Run it in the background (or a separate shell) so you can drive `agent-browser` against it.

If `app.yaml` declares env vars with `valueFrom` (referencing bundle resources like SQL warehouse IDs or Genie space IDs), `run-local` will exit with `... defined in app.yaml with valueFrom property and can't be resolved locally`. Pass each as `--env KEY=value`; values come from `databricks.yml` `targets.<target>.variables`.

Wait until the proxy is reachable before scripting against it:

```bash
until curl -fsS "http://localhost:8001/" -o /dev/null; do sleep 1; done
```

Then drive it with `agent-browser open http://localhost:8001` (see "Driving with agent-browser" below).

## Driving a deployed app (real URL, real auth)

For URLs like `https://<name>.<workspace>.databricksapps.com`, `run-local`'s header-injection trick doesn't apply — the platform demands real OAuth/SSO. Pick one of the following.

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

Once a session is open (local or deployed), the browser persists across commands:

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

## Shutdown

- **Local app**: send SIGINT (Ctrl+C) to `run-local`. It forwards SIGTERM to the app and waits up to **15 seconds** before SIGKILL — same grace window the Apps platform uses, so handlers behave the same locally and in prod.
- **agent-browser session**: `agent-browser close` to terminate the daemon.

## What the local proxy actually does

`run-local` starts an HTTP proxy on `localhost:<port>` (default 8001) in front of the app (default `localhost:8000`). On every forwarded request it injects:

| Header | Value |
|---|---|
| `X-Forwarded-Host` | `localhost` |
| `X-Forwarded-User` | CLI user's `userName` |
| `X-Forwarded-Email` | CLI user's primary email (or `userName` if none) |
| `X-Forwarded-Preferred-Username` | CLI user's `displayName` |
| `X-Real-Ip` | `127.0.0.1` |
| `X-Request-Id` | fresh UUID per request |

These are the same headers the Apps platform's auth proxy sets in production, so AppKit (and any framework that reads `X-Forwarded-*`) treats the request as authenticated. The identity comes from `WorkspaceClient.CurrentUser.Me()` — i.e. whichever profile is active.

The proxy injects identity headers but **not** an OBO user token. AppKit plugins or app code that requires an OBO token (anything calling `.asUser(req)` or reading a `user_api_scopes` token) will fail under `run-local`. For OBO-dependent flows, drive the deployed app instead.

## Gotchas

| Symptom | Cause | Fix |
|---|---|---|
| App redirects to OAuth instead of loading (local mode) | Framework isn't honoring `X-Forwarded-*`, or you bypassed the proxy and hit `--app-port` directly | Hit the **proxy** port (`--port`, default 8001), not the app port (`--app-port`, default 8000). For AppKit, ensure the version respects forwarded headers in dev. |
| `address already in use` on start | Default port 8001 (or 8000) is taken | Pass `--port` and/or `--app-port` to free values. |
| App keeps running after Ctrl+C | App ignored SIGTERM | Wait 15s — `run-local` escalates to SIGKILL. Fix the handler in the app. |
| Wrong user identity in the app | `databricks` is using a different profile than expected | Pass `--profile <PROFILE>` to `run-local`; verify with `databricks current-user me --profile <PROFILE>`. |
| `prepare-environment` fails | `uv` not installed | Install `uv`, or skip the flag and prepare deps yourself. For Node-only apps `npm install` is enough. |
| `... defined in app.yaml with valueFrom property and can't be resolved locally` | `app.yaml` references bundle resources (warehouse, Genie space) that don't resolve outside a deployed bundle | Pass each `valueFrom` env var as `--env KEY=value`; values live in `databricks.yml` under `targets.<target>.variables`. |
| `app.yaml` not found / spec not picked up | AppKit scaffolds use `app.yaml`; older defaults look for `app.yml` | Pass `--entry-point app.yaml`. |
| AppKit app crashes on `run-local` with `AuthenticationError: Missing user token in request headers` | Proxy injects `X-Forwarded-*` identity but no OBO token; plugins requiring a user token reject this | Either run `npm run dev` instead, or drive the **deployed** app. The local proxy can't synthesize an OBO token. |
| Deployed mode: `No running Chrome instance found. Launch Chrome with --remote-debugging-port` | A regular Chrome window has no debug port. Relaunching Chrome with the flag while it's already running just opens a new tab in the existing instance (`Opening in existing browser session`) — it does NOT add the flag | Fully quit Chrome (`osascript -e 'quit app "Google Chrome"'`), then `open -a "Google Chrome" --args --remote-debugging-port=9222`. Or simpler: switch to `--headed --profile`. |
| `⚠ --profile, --headed ignored: daemon already running` | A previous agent-browser run left the daemon up | `agent-browser close` first, then re-open with the desired flags. |

## Two-port summary (local mode — don't mix these up)

- **`--port` (default 8001)** — the **proxy**. This is the URL you give to `agent-browser` and the URL printed by `run-local`. All traffic here gets the `X-Forwarded-*` headers.
- **`--app-port` (default 8000)** — the **app's own bind port**. The proxy forwards to this. Hitting it directly skips auth header injection — usually not what you want.
