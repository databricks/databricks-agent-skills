# Genie / AI-result trust patterns (copy these)

> **GATE:** apply ONLY if the app exposes a Genie / chat / natural-language query surface. If it's a
> dashboard / report / KPI app with no NL/chat input, do not load or apply any pattern here.

An AI/Genie answer is only trustworthy if the user can **see how it was produced** and **who it ran as**.
For ANY Genie / chat / natural-language data surface, ship ALL FIVE below — "use `GenieChat` and show
a spinner" is not enough. Snippets use the real `@databricks/appkit` + `@databricks/appkit-ui` APIs.

## 1. Authenticated identity (who is asking)
Databricks injects identity headers; expose them and show the signed-in caller. Use the real
platform headers — `x-forwarded-email` (email) and `x-forwarded-user` (user identifier):
```ts
// server/server.ts
app.get("/api/whoami", (req, res) => {
  res.json({
    email: req.header("x-forwarded-email") ?? null,
    user: req.header("x-forwarded-user") ?? null,
  });
});
```
```tsx
const [me, setMe] = useState<{ email?: string } | null>(null);
useEffect(() => { fetch("/api/whoami").then(r => (r.ok ? r.json() : null)).then(setMe).catch(() => {}); }, []);
<Badge variant="secondary">{me?.email ?? "Signed in"}</Badge>
```
**Whether queries actually run as that user (OBO) depends on config:** a default `genie()` runs as the
app's *service principal*. To run on-behalf-of the user, declare `user_api_scopes: [dashboards.genie]`
in `databricks.yml` (see the parent `databricks-apps` `genie.md`). Only claim OBO in the UI when that's
wired — otherwise disclose service-principal execution (see #5).

Register the plugin with `genie()` (no args); it reads `DATABRICKS_GENIE_SPACE_ID` from the env, per the
parent `genie.md`. (Multi-space config: `npx @databricks/appkit docs ./docs/plugins/genie.md`.)

## 2. Show the generated SQL (never hide how the answer was produced)
`useGenieChat` messages carry attachments with the generated query (exact shape is versioned — see
`npx @databricks/appkit docs ./docs/plugins/genie.md`, the "useGenieChat hook" section). Render the SQL inspectably:
```tsx
const lastSql = useMemo(() => {
  for (const m of [...messages].reverse())
    for (const a of m.attachments ?? []) if (a.query) return a.query;
  return null;
}, [messages]);

{lastSql && (
  <Card>
    <CardHeader><CardTitle>Generated SQL</CardTitle>
      <CardDescription>{lastSql.title ?? "How this answer was computed"}</CardDescription></CardHeader>
    <CardContent><pre className="overflow-auto text-xs">{lastSql.query}</pre></CardContent>
  </Card>
)}
```

## 3. Streaming / status — not a frozen spinner
Reflect `useGenieChat().status` — its exact union is versioned, so don't hard-code the values
(`npx @databricks/appkit docs ./docs/plugins/genie.md`). Surface progress + errors, never a frozen spinner:
```tsx
const { messages, status, sendMessage, error } = useGenieChat({ alias: "default" });
{status === "streaming" && <p className="text-muted-foreground">Analyzing your data…</p>}
{status === "error" && <Alert variant="destructive">{error ?? "Genie failed — rephrase or retry."}</Alert>}
```

## 4. Disclaimer on every AI answer
Persistent, low-key, near the chat — AI-generated, may be wrong, verify against the SQL/source:
```tsx
<p className="text-xs text-muted-foreground">
  AI-generated from your data via Genie — review the generated SQL before trusting results.
</p>
```

## 5. Governance + empty/ambiguous states
- **Match the disclosure to the real execution identity (per #1):** if `user_api_scopes: [dashboards.genie]` is wired, state that access is governed by the user's own permissions (OBO); if not, disclose that queries run as the app's service principal. Never render an OBO claim the config doesn't back.
- If results are empty/ambiguous, say so with `Empty` — never render a blank table or imply a wrong answer.

**Required checklist (all five):** identity shown · generated SQL inspectable · streaming/status surfaced ·
per-answer disclaimer · execution identity disclosed truthfully (OBO only when `user_api_scopes` is wired, else service principal) + empty/error states. A Genie page missing any of these is incomplete.
