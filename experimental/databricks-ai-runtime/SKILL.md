---
name: databricks-ai-runtime
description: "Databricks AI Runtime, the `databricks air` CLI commands for submitting and managing GPU training workloads on Databricks serverless compute. Use for: writing and submitting `databricks air` workload YAML, passing hyperparameters and secrets, checking run status, listing/cancelling runs, streaming a run's logs and watching its progress, custom Docker image setup, and environment configuration."
compatibility: Requires the Databricks CLI with the `air` command. See the [installation guide](https://docs.databricks.com/aws/en/machine-learning/ai-runtime/cli/installation) to get started.
metadata:
  version: "0.2.0"
---

# Databricks AI Runtime (`databricks air`)

Databricks AI Runtime is a set of `databricks air` CLI commands for submitting GPU training workloads to Databricks serverless compute. It manages environment setup, distributed training configuration, and workload lifecycle, without requiring you to manage clusters or infrastructure.

This skill covers the three everyday flows: **starting a run**, **checking on a run**, and **monitoring a run** as it trains.

## Reference discipline

The CLI's built-in help is the source of truth for field names, GPU types,
on-cluster environment variables, and constraints. Prefer it at runtime over
anything memorized. Look up a config field by passing its path to `-h` on the
`run` command (the path is a separate argument):

```bash
databricks air run -h config                              # list the YAML fields
databricks air run -h config.compute                      # one field
databricks air run -h config.compute.accelerator_type     # a nested field
```

`databricks air <subcommand> --help` documents each command's flags. This skill
covers workflow and the few things the help does not spell out.

## Session setup

Confirm the command is available and list your Databricks config profiles:

```bash
databricks air --help
databricks auth profiles --skip-validate    # available Databricks config profiles
```

Pass `-p <profile>` on every command. Add `-o json` for scripted/programmatic
calls so you get a structured envelope instead of human text:

- **Success**: `{"v": 1, "ts": "...", "data": {...}}`
- **Error**: `{"v": 1, "ts": "...", "error": {"code": "...", "kind": "...", "message": "...", "retryable": bool}}`

Config validation (input) errors are the exception: they print as plain text to
stderr with a non-zero exit even under `-o json`, so check the exit code and
stderr too, not just the parsed JSON. When you do get a structured error, its
`kind` tells you what to do:

| kind | Meaning | Action |
|---|---|---|
| `PERMANENT` | Not authenticated / permission denied / non-retryable | If auth: `databricks auth login --host <workspace-url>` |
| `NOT_FOUND` | Bad run ID / resource | Check the input |
| `CONFLICT` | Idempotency key collision | Use a new `--idempotency-key` |
| `TRANSIENT` | Retryable | Retry |

## Subcommands

| Command | What it does |
|---|---|
| `databricks air run` | Submit a workload from a YAML file. Add `--watch` to stream logs until it finishes. |
| `databricks air get <JOB_RUN_ID>` | Show status, config, and timing for one run. |
| `databricks air list` | List your active runs (add `--all-status` for finished, `--all-users`, `--filter`, `--limit`). |
| `databricks air cancel <JOB_RUN_ID> [<JOB_RUN_ID>...]` / `... --all` | Cancel one or more runs, or all of your active runs. |
| `databricks air logs <JOB_RUN_ID>` | Stream a running run's logs, or fetch a finished run's logs. |

For flags and defaults, run `databricks air <subcommand> --help`.

## Workload YAML

```yaml
experiment_name: my-training-job     # alphanumeric, - and _ only
compute:
  num_accelerators: 1
  accelerator_type: GPU_1xA10        # run `databricks air run -h config.compute` for valid values
environment:
  version: "5"                       # client image version; prefix "databricks_ai_v" to also load the ML venv
  dependencies:
    - mlflow
code_source:
  type: snapshot
  snapshot:
    root_path: "."                   # snapshot this dir; extracted to $CODE_SOURCE_PATH on each node
command: |-
  cd "$CODE_SOURCE_PATH"
  python train.py
```

Submit with `databricks air run --file workload.yaml -p <profile>`. Field
details live in `databricks air run -h config.<field>` (the authoritative
source). Today's accelerator types are `GPU_1xA10` and `GPU_8xH100`; confirm
with `databricks air run -h config.compute`.

## Configuring the workload

These optional top-level fields cover the common needs. Run
`databricks air run -h config.<field>` for the full reference on any of them.

### Environment variables and secrets

Set plain values under `env_variables`; pull sensitive values from Databricks
Secrets under `secrets` (each entry maps an env var name to a `scope/key`, and
the value is materialized on the worker, never logged):

```yaml
env_variables:
  BATCH_SIZE: "32"
secrets:
  HF_TOKEN: my_scope/hf_token          # -> $HF_TOKEN on every node
  WANDB_API_KEY: my_scope/wandb_key
```

The scope and key must already exist; create them once with the Databricks CLI:

```bash
databricks secrets create-scope my_scope -p <profile>
databricks secrets put-secret my_scope hf_token -p <profile>
```

Secret env var names must not collide with `env_variables` names.

### Parameters (hyperparameters)

`parameters` is the clean way to pass hyperparameters into your script and
change them between runs without editing training code. The CLI writes them to
a YAML file on the cluster and exposes its path as `$HYPERPARAMETERS_PATH`:

```yaml
parameters:
  learning_rate: 0.001
  batch_size: 32
  warmup_steps: 1000
  use_amp: true
```

Read them in the script:

```python
import os, yaml
with open(os.environ["HYPERPARAMETERS_PATH"]) as f:
    hp = yaml.safe_load(f)
lr = hp["learning_rate"]
```

Values can be strings, numbers, booleans, lists, or nested dicts. To sweep a
hyperparameter, resubmit with the value changed (and a fresh idempotency key).

### Retries

Failed attempts are retried automatically: `max_retries` has a non-zero default
(check the current value with `databricks air run -h config.max_retries`). Set
`max_retries: 0` to fail immediately without retrying. When `timeout_minutes` is
set, it applies per-attempt.

### Permissions

By default only you can see the run. Grant others access to the submitted job
with `permissions` (DABs-compatible format); levels are `CAN_VIEW`,
`CAN_MANAGE_RUN`, `CAN_MANAGE`:

```yaml
permissions:
  - group_name: data-engineering
    level: CAN_VIEW
  - user_name: alice@example.com
    level: CAN_MANAGE
```

## Environment variables provided on each node

`databricks air` sets these automatically on every node; use them in `command:`
and in your training code. Confirm the current list with
`databricks air run -h config.command`.

| Variable | Meaning |
|---|---|
| `CODE_SOURCE_PATH` | Absolute path to your extracted `code_source` on the node (`cd $CODE_SOURCE_PATH`). |
| `MASTER_ADDR` / `MASTER_PORT` | Address/port of the rank-0 node for distributed coordination. |
| `NUM_NODES` | Total number of nodes. |
| `NODE_RANK` | Rank of the current node (0 to `NUM_NODES`-1). |
| `WORLD_SIZE` | Total number of GPUs across all nodes. |
| `LOCAL_WORLD_SIZE` | Number of GPUs on this node. |
| `MLFLOW_RUN_ID` | MLflow run ID for this job (log metrics/artifacts to it). |
| `HYPERPARAMETERS_PATH` | Path to the `parameters` YAML file (only set when `parameters:` is defined). |

Your `command:` runs **once per node**, so per-process ranks (`RANK`,
`LOCAL_RANK`) are **not** set by the platform. Your distributed launcher
(torchrun, accelerate) assigns them when it spawns one process per GPU; pass it
`$NODE_RANK` / `$NUM_NODES` / `$MASTER_ADDR` / `$MASTER_PORT`.

## Starting a run

1. **Turn the user's intent into the YAML.** Extract model, dataset path, GPU
   count and type, and the training command from the request. Ask before
   synthesizing a config when something critical is ambiguous (data path,
   checkpoint dir, custom image).

2. **Write the `command:`** using the env vars above. Common launch shapes:

   | Framework | `command:` shape |
   |---|---|
   | plain torch, single GPU | `python train.py` |
   | torch, multi-GPU (1 node) | `torchrun --nproc_per_node=$LOCAL_WORLD_SIZE train.py` |
   | torch, multi-node | `torchrun --nnodes=$NUM_NODES --nproc_per_node=$LOCAL_WORLD_SIZE --node_rank=$NODE_RANK --master_addr=$MASTER_ADDR --master_port=$MASTER_PORT train.py` |
   | HuggingFace Accelerate | `accelerate launch --config_file accelerate.yaml train.py` |
   | DeepSpeed | `deepspeed --num_gpus=$LOCAL_WORLD_SIZE train.py` |
   | Composer / MosaicML | `composer train.py` |

   Multi-line commands go under `command: |-`. Access uploaded code via
   `$CODE_SOURCE_PATH`. **Total GPUs = nodes x accelerators-per-node**; the
   per-node count for a type comes from `databricks air run -h config.compute`,
   so make `num_accelerators` a valid multiple of it.

3. **Pre-flight the referenced resources** so the job does not die on startup:
   confirm every `secrets` scope/key exists (`databricks secrets list-scopes` /
   `list-secrets <scope>`), and if `environment.docker_image` is set, that the
   image is registered with Databricks (see [docker-images.md](docker-images.md)).

4. **Dry-run before submitting.** This validates the config without launching:
   ```bash
   databricks air run --file workload.yaml --dry-run -o json -p <profile>
   ```
   A config-validation error is a hard stop: it prints as plain text on stderr
   with a non-zero exit, so show that message to the user and fix the YAML.
   Other failures are infra/auth and should bubble up.

5. **Submit.** Use a stable `--idempotency-key` so an accidental re-run does not
   double-submit (compose it from `<user>-<experiment>-<YYYYMMDD>-v<N>` and bump
   `vN` on each resubmit; avoid dynamic subexpressions like `$(uuidgen)` so the
   command stays auto-approvable):
   ```bash
   databricks air run --file workload.yaml \
     --idempotency-key <key> -o json -p <profile>
   ```
   Add `--watch` to stream logs to your terminal until the run finishes. Capture
   `data.run_id` from the response, then monitor it.

## Checking on a run

```bash
databricks air get <JOB_RUN_ID> -o json -p <profile>   # status, config, timing
databricks air list -o json -p <profile>               # your active runs (add --all-status for finished)
```

## Monitoring a run

**Stream logs while it runs.** The simplest path is to submit with `--watch`,
which streams the run's logs to your terminal until it reaches a terminal state:

```bash
databricks air run --file workload.yaml --watch -p <profile>
```

For a run that is already going, stream its logs by ID:

```bash
databricks air logs <JOB_RUN_ID> -p <profile>
# --node N (one node), --lines N (last N lines of a finished run),
# --minutes N (last N minutes), --download-to DIR (save all nodes' logs)
```

**Loss, GPU utilization, and metric history live in MLflow.** The CLI streams
logs and status, not training metrics. The submit/status response includes the
MLflow experiment and run URL; echo it so the user can open the run in the
Databricks UI for loss curves, GPU utilization, and system charts.

## If a run fails

Pull the logs and surface the actual error to the user:

```bash
databricks air logs <JOB_RUN_ID> -p <profile>
```

Show the failing traceback and let the user decide the fix. For a deeper,
guided diagnosis of a training failure, use AI Runtime's own debugging support
rather than guessing at root cause here.

## Custom Docker images

Use a custom Docker image instead of `environment.version` when your workload
needs specific system libraries, CUDA extensions (flash-attn, apex, custom
kernels), or dependencies that do not fit `environment.dependencies`.

**Read [docker-images.md](docker-images.md)** for step-by-step guidance on:

- Using Databricks-provided base images
- Dockerfile patterns
- Pre-build compatibility checklist (CUDA/driver, PyTorch, NCCL, EFA/RDMA)
- Registering images with Databricks
