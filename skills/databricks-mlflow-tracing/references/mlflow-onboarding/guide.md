---
name: mlflow-onboarding
description: Onboards users to MLflow by determining their use case (GenAI agents/apps or traditional ML/deep learning) and guiding them through relevant quickstart tutorials and initial integration. If an experiment ID is available, it should be supplied as input to help determine the use case. Use when the user asks to get started with MLflow, set up tracking, add observability, or integrate MLflow into their project. Triggers on "get started with MLflow", "set up MLflow", "onboard to MLflow", "add MLflow to my project", "how do I use MLflow".
---

# MLflow Onboarding

Choose the onboarding path that matches the user’s project:

- **GenAI apps and agents** — tracing, evaluation, and prompt management for chatbots, RAG pipelines, and tool-calling agents.
- **Traditional ML / deep learning** — experiment tracking, model logging, and deployment for scikit-learn, PyTorch, TensorFlow, XGBoost, and other training frameworks.

## Reuse existing configuration

Reuse a working tracking URI and experiment, including configuration supplied by
Databricks tooling. Resolve only missing configuration or a requested backend change;
do not replace the supplied profile, credentials or experiment.

## Step 1: Determine the Use Case

Check these signals in order. **Ask the user if the use case is still unclear.**

### Signal 1: Check the Codebase

Search the user's project for imports and usage patterns that indicate the use case:

**GenAI indicators:**
- Imports from LLM client libraries: `openai`, `anthropic`, `google.generativeai`, `google.genai`, `langchain`, `langchain_openai`, `langgraph`, `llamaindex`, `litellm`, `autogen`, `crewai`, `dspy`
- Imports from MLflow GenAI modules: `mlflow.genai`, `mlflow.tracing`, `mlflow.openai`, `mlflow.langchain`
- Usage of chat completions, embeddings, or agent frameworks
- Prompt templates or prompt engineering code

**Traditional ML indicators:**
- Imports from ML frameworks: `sklearn`, `torch`, `tensorflow`, `keras`, `xgboost`, `lightgbm`, `catboost`, `statsmodels`, `scipy`
- Imports from MLflow ML modules: `mlflow.sklearn`, `mlflow.pytorch`, `mlflow.tensorflow`
- Model training loops, `.fit()` calls, hyperparameter tuning code
- Dataset loading with tabular/image/time-series data

```bash
# Search for GenAI indicators
grep -rl --include='*.py' -E '(import openai|import anthropic|from langchain|from langgraph|import litellm|from mlflow\.genai|from mlflow\.tracing|mlflow\.openai|mlflow\.langchain|ChatCompletion|chat\.completions)' .

# Search for ML indicators
grep -rl --include='*.py' -E '(from sklearn|import torch|import tensorflow|import keras|import xgboost|import lightgbm|mlflow\.sklearn|mlflow\.pytorch|mlflow\.tensorflow|\.fit\()' .
```

### Signal 2: Check the Experiment Type Tag

If the codebase or project directory is the MLflow repository itself, skip to Signal 3 — the MLflow repo contains code for all use cases and does not indicate the user's intent.

If the experiment ID is known, check its `mlflow.experimentKind` tag:

```bash
mlflow experiments get --experiment-id <EXPERIMENT_ID> --output json > /tmp/exp_detail.json
jq -r '.tags["mlflow.experimentKind"] // "not set"' /tmp/exp_detail.json
```

- **`genai_development`** → GenAI use case
- **`custom_model_development`** → Traditional ML use case
- **Not set** → Proceed to Signal 3

If the experiment ID is not known, skip to Signal 3.

### Signal 3: Ask the User

If the codebase and experiment signals are inconclusive, ask directly:

> Are you building a **GenAI application** (e.g., an LLM-powered chatbot, RAG pipeline, or tool-calling agent) or a **traditional ML/deep learning model** (e.g., training a classifier, regression model, or neural network)?

**Do not guess the use case.**

## Step 2: Recommend Quickstart Tutorials

Recommend the quickstart that fits the project. Ask whether the user wants a walkthrough or direct integration.

### GenAI Path

The MLflow GenAI documentation is at: https://mlflow.org/docs/latest/genai/getting-started/

Choose the relevant guide:

- **Tracing Quickstart** (https://mlflow.org/docs/latest/genai/tracing/quickstart/) — Enabling automatic tracing for LLM calls. Covers starting an MLflow server, creating an experiment, enabling autologging, and viewing traces in the UI.
  - Python + OpenAI variant: https://mlflow.org/docs/latest/genai/tracing/quickstart/python-openai/
  - TypeScript + OpenAI variant: https://mlflow.org/docs/latest/genai/tracing/quickstart/typescript-openai
  - OpenTelemetry (language-agnostic) variant: also linked from the quickstart page
- **Evaluation Quickstart** (https://mlflow.org/docs/latest/genai/eval-monitor/quickstart/) — Evaluating GenAI application quality using LLM judges (scorers). Covers defining datasets, prediction functions, and built-in + custom scorers.
- **Version Tracking Quickstart** (https://mlflow.org/docs/latest/genai/version-tracking/quickstart/) — Prompt management, application versioning, and connecting tracing to versioned prompts.

If none of these match the user's needs, look up the MLflow GenAI documentation for more relevant guides.

### Traditional ML Path

The MLflow ML documentation is at: https://mlflow.org/docs/latest/ml/getting-started/

Choose the relevant guide:

- **Tracking Quickstart** (https://mlflow.org/docs/latest/ml/tracking/quickstart/) — Experiment tracking with scikit-learn: autologging, manual parameter/metric/model logging, and exploring results in the MLflow UI.
- **Deep Learning Tutorial** (https://mlflow.org/docs/latest/ml/getting-started/deep-learning/) — Training a PyTorch model with MLflow logging: parameters, metrics, checkpoints, and system metrics (GPU utilization, memory).
- **Hyperparameter Tuning Tutorial** (https://mlflow.org/docs/latest/ml/getting-started/hyperparameter-tuning/) — Running hyperparameter searches with Optuna + MLflow, comparing results, and selecting the best model.

If none of these match the user's needs, look up the MLflow ML documentation for more relevant guides.

## Step 3: Integrate MLflow

After the tutorial, or if the user skips it, offer direct integration. **Always ask for the user's consent before changing their code.**

### GenAI Integration

The core integration for GenAI apps is **tracing** — capturing LLM calls, tool invocations, and agent steps automatically.

**If asked to create an example project:** Do not assume the user has LLM API keys (e.g., OpenAI, Anthropic). Instead, create traces with mock data using `@mlflow.trace` and `mlflow.start_span()` to demonstrate tracing without requiring external API access. For example:

```python
import mlflow

mlflow.set_experiment("example-genai-app")

@mlflow.trace
def mock_chat(query: str) -> str:
    with mlflow.start_span(name="retrieve_context") as span:
        context = "Mock retrieved context for: " + query
        span.set_inputs({"query": query})
        span.set_outputs({"context": context})
    with mlflow.start_span(name="generate_response") as span:
        response = "Mock response based on: " + context
        span.set_inputs({"context": context, "query": query})
        span.set_outputs({"response": response})
    return response

mock_chat("What is MLflow?")
```

**What to set up (for an existing project):**

1. **Autologging** — If the user's code uses a supported framework, a single line automatically traces all calls to their LLM provider. See https://mlflow.org/docs/latest/genai/tracing/ for the full list of supported providers. If the provider is supported:

   ```python
   import mlflow

   # Pick the one that matches the user's LLM provider:
   mlflow.openai.autolog()       # OpenAI SDK
   mlflow.anthropic.autolog()    # Anthropic SDK
   mlflow.gemini.autolog()       # Google Gemini (google-genai SDK)
   mlflow.langchain.autolog()    # LangChain / LangGraph
   mlflow.litellm.autolog()      # LiteLLM
   ```

   Add this call once at application startup (e.g., top of `main.py`, `app.py`, or the entry point module). It must execute before any LLM calls are made.

   If the provider is **not** supported by autologging, skip to step 3 (Custom tracing) and use `@mlflow.trace` to manually instrument the relevant functions.

2. **Experiment configuration** — Set the experiment so traces are organized:

   ```python
   mlflow.set_experiment("my-genai-app")
   ```

   Or via environment variable: `export MLFLOW_EXPERIMENT_NAME="my-genai-app"`

3. **Custom tracing** (optional) — For functions that aren't automatically traced (custom tools, business logic), use the `@mlflow.trace` decorator:

   ```python
   @mlflow.trace
   def my_custom_tool(query: str) -> str:
       # ... tool logic ...
       return result
   ```

**Where to add it:** Find the application's entry point or initialization module and add the autologging call there. Search for the main LLM client instantiation (e.g., `openai.OpenAI()`, `ChatOpenAI()`) to find the right location.

4. **Prompt Registry** (optional) — MLflow can version, store, and load prompts so application code loads a prompt by URI instead of hard-coding the template.

   ```python
   import mlflow

   # Register a prompt version
   prompt_version = mlflow.genai.register_prompt(
       name="my_prompt",
       template="Answer the user's question: {{question}}",
   )
   print(prompt_version.uri)  # prompts:/my_prompt/1

   # Load it back in application code
   prompt = mlflow.genai.load_prompt("prompts:/my_prompt/1")
   ```

   **On Databricks (Unity Catalog):** prompts are stored under a UC `catalog.schema`, so `name` is a three-part `catalog.schema.my_prompt` and the workspace must have the Prompt Registry preview enabled (account admin -> Previews -> "Prompt Registry"). On success `register_prompt` logs a workspace UI link and auto-links the active experiment's Prompts tab to `catalog.schema`. If that tab is empty after registering, the active experiment was not auto-linked (older mlflow versions do not set this tag automatically). Set it manually:

   ```python
   mlflow.set_experiment_tag(
       "mlflow.promptRegistryLocation",
       "catalog.schema",  # two-part: catalog.schema (no prompt name)
   )
   ```

### Traditional ML Integration

The core integration for ML is **experiment tracking** — capturing parameters, metrics, and models from training runs.

**What to set up:**

1. **Autologging** — If the user's code uses a supported framework, a single line automatically logs parameters, metrics, and models during training. See https://mlflow.org/docs/latest/ml/ for the full list of supported frameworks. If the framework is supported:

   ```python
   import mlflow

   # Pick the one that matches the user's ML framework:
   mlflow.sklearn.autolog()      # scikit-learn
   mlflow.pytorch.autolog()      # PyTorch / PyTorch Lightning
   mlflow.tensorflow.autolog()   # TensorFlow / Keras
   mlflow.xgboost.autolog()      # XGBoost
   mlflow.lightgbm.autolog()     # LightGBM
   ```

   Add this call once before training starts. It automatically captures `model.fit()` calls, logged metrics, and model artifacts.

   If the framework is **not** supported by autologging, skip to step 3 (Manual logging) and use `mlflow.log_param()`, `mlflow.log_metric()`, and `mlflow.log_artifact()` to log data explicitly.

2. **Experiment configuration** — Set the experiment so runs are organized:

   ```python
   mlflow.set_experiment("my-ml-experiment")
   ```

   Or via environment variable: `export MLFLOW_EXPERIMENT_NAME="my-ml-experiment"`

3. **Manual logging** (optional) — For metrics or parameters not captured by autologging:

   ```python
   with mlflow.start_run():
       mlflow.log_param("custom_param", value)
       mlflow.log_metric("custom_metric", value)
   ```

**Where to add it:** Find the training script or module where `model.fit()` (or equivalent) is called. Add the autologging call before the training loop begins.

## Verification

### GenAI Verification

Follow the [verification workflow in `mlflow-trace-instrumentation`](../mlflow-trace-instrumentation/guide.md#verification). Run the instrumented application once, then enforce a 60-second wall-clock deadline for readback: fetch the captured trace ID, or search with a `trace.timestamp_ms` bound from the run start and `max_results=1`. Cancel the verification command when that deadline expires, even if an MLflow call is still waiting or retrying internally. Retry at most once after a concrete, quick fix within the original budget. Stop once the trace and expected spans are confirmed; an additional visual audit is unnecessary.

If execution or readback is blocked by a missing API key, authentication, permissions, or a slow/unavailable SQL warehouse, hand back the verified steps, the unverified result, the observed error, and the specific user action needed. Do not keep rerunning the app or try SQL, raw REST, or alternate authentication paths to finish verification.

### ML Verification

1. Run the training script
2. Check for runs:
   ```bash
   python - <<'PY'
   from mlflow.tracking import MlflowClient
   print(len(MlflowClient().search_runs(["<EXPERIMENT_ID>"], max_results=5)))
   PY
   ```
3. If runs appear, open the MLflow UI to inspect logged parameters, metrics, and artifacts
