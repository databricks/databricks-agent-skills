# Genie / AI-result trust patterns (copy these)

An AI/Genie answer is only trustworthy if the user can **see how it was produced** and **who it ran as**.
For ANY Genie / chat / natural-language data surface, ship ALL FIVE below — "use `GenieChat` and show
a spinner" is not enough. Snippets use the real `@databricks/appkit` + `@databricks/appkit-ui` APIs.

## 1. Authenticated identity (who is asking — on-behalf-of)
Databricks injects identity headers; expose them and show the caller. Queries run as that user (OBO).
```ts
// server/server.ts
app.get("/api/whoami", (req, res) => {
  res.json({
    email: req.header("x-forwarded-email") ?? req.header("x-forwarded-user") ?? null,
    userId: req.header("x-databricks-user-id") ?? null,
  });
});
```
```tsx
const [me, setMe] = useState<{ email?: string } | null>(null);
useEffect(() => { fetch("/api/whoami").then(r => r.json()).then(setMe).catch(() => {}); }, []);
<Badge variant="secondary">{me?.email ?? "Signed in"}</Badge>
```
Configure the space explicitly server-side: `genie({ spaces: { default: process.env.DATABRICKS_GENIE_SPACE_ID } })`.

## 2. Show the generated SQL (never hide how the answer was produced)
`useGenieChat` messages carry `attachments[].query` / `queryResults`. Render the SQL inspectably:
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
`useGenieChat().status ∈ "idle" | "loading-history" | "streaming" | "error"`. Reflect it:
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
- State that access is governed by the user's own permissions (OBO), per #1.
- If results are empty/ambiguous, say so with `Empty` — never render a blank table or imply a wrong answer.

**Required checklist (all five):** identity shown · generated SQL inspectable · streaming/status surfaced ·
per-answer disclaimer · governed/OBO + empty/error states. A Genie page missing any of these is incomplete.
