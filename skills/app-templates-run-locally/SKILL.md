---
name: app-templates-run-locally
description: "Run and test the agent locally. Use when: (1) User says 'run locally', 'start server', 'test agent', or 'localhost', (2) Need curl commands to test API, (3) Troubleshooting local development issues, (4) Configuring server options like port or hot-reload."
---

# Run Agent Locally

## Start the Server

```bash
uv run start-app
```

This starts the agent at http://localhost:8000

## Server Options

```bash
# Hot-reload on code changes (development)
uv run start-server --reload

# Custom port
uv run start-server --port 8001

# Multiple workers (production-like)
uv run start-server --workers 4

# Combine options
uv run start-server --reload --port 8001
```

## Test the API

**Streaming request:**
```bash
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{ "input": [{ "role": "user", "content": "hi" }], "stream": true }'
```

**Non-streaming request:**
```bash
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{ "input": [{ "role": "user", "content": "hi" }] }'
```

## Run Evaluation

```bash
uv run agent-evaluate
```

Uses MLflow scorers (RelevanceToQuery, Safety).

## Run Unit Tests

```bash
pytest [path]
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **Port already in use** | Use `--port 8001` or kill existing process |
| **Authentication errors** | Verify `.env` is correct; run **app-templates-quickstart** skill |
| **Module not found** | Run `uv sync` to install dependencies |
| **MLflow experiment not found** | Ensure `MLFLOW_TRACKING_URI` in `.env` is `databricks://<profile-name>` |

### MLflow Experiment Not Found

If you see: "The provided MLFLOW_EXPERIMENT_ID environment variable value does not exist"

**Verify the experiment exists:**
```bash
databricks -p <profile> experiments get-experiment <experiment_id>
```

**Fix:** Ensure `.env` has the correct tracking URI format:
```bash
MLFLOW_TRACKING_URI="databricks://DEFAULT"  # Include profile name
```

The quickstart script configures this automatically. If you manually edited `.env`, ensure the profile name is included.

## Next Steps

- Modify your agent: see **modify-agent** skill
- Deploy to Databricks: see **app-templates-deploy** skill
