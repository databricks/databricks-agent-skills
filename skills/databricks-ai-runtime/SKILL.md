---
name: databricks-ai-runtime
description: "Databricks AI Runtime, the `databricks air` CLI commands for submitting and managing GPU training workloads on Databricks serverless compute. Use for: writing and submitting `databricks air` workload YAML, choosing an accelerator type and Python environment, passing hyperparameters and secrets, configuring retries, checking run status, listing/cancelling runs, streaming a run's logs and watching its progress, debugging failed runs, GPU pools, multi-container workloads, custom Docker image setup, and converting a workload to a Databricks Asset Bundle."
compatibility: Requires the Databricks CLI with the air command. Flattened code_source, multi-container workloads, and workspace-validated dry runs require CLI 1.20.0 or newer; older CLIs can use the nested snapshot format documented below. Listing the accelerator types available in your workspace requires CLI 1.23.0 or newer. See the [installation guide](https://docs.databricks.com/dev-tools/cli/install).
metadata:
  version: "0.3.0"
---

# Databricks AI Runtime (`databricks air`)

Databricks AI Runtime is a set of `databricks air` CLI commands for submitting GPU training workloads to Databricks serverless compute. It manages environment setup, distributed training configuration, and workload lifecycle, without requiring you to manage clusters or infrastructure.

This skill covers the three everyday flows: **starting a run**, **checking on a run**, and **monitoring a run** as it trains.

## Reference discipline

The CLI's built-in help is the source of truth for field names, accelerator
types, defaults, and constraints. Prefer it at runtime over anything memorized.
Look up a config field by passing its path to `-h` on the `run` command (the
path is a separate argument):

```bash
databricks air run -h config                              # list the YAML fields
databricks air run -h config.compute                      # one field
databricks air run -h config.compute.accelerator_type     # a nested field
```

`databricks air <subcommand> --help` documents each command's flags. This skill
covers workflow and the few things the help does not spell out.

## Session setup

Check the CLI version, confirm the command is available, and list your
Databricks config profiles:

```bash
databricks version
databricks air --help
databricks auth profiles --skip-validate    # available Databricks config profiles
```

The examples use flattened `code_source` fields, available in
[Databricks CLI 1.20.0 and newer](https://github.com/databricks/cli/releases/tag/v1.20.0).
On an older CLI, use the equivalent nested snapshot format shown under
[Workload YAML](#workload-yaml). CLI 1.20.0 and newer accept both formats.
Do not mix nested and flattened fields in the same configuration.

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
| `PERMANENT` | Not authenticated / permission denied / feature disabled / non-retryable | If auth: `databricks auth login --host <workspace-url>` |
| `NOT_FOUND` | Bad run ID / resource | Check the input |
| `CONFLICT` | Idempotency key collision | Use a new `--idempotency-key` |
| `TRANSIENT` | Retryable | Retry |

## Subcommands

| Command | What it does |
|---|---|
| `databricks air run` | Submit a workload from a YAML file. Add `--watch` to stream logs until it finishes, `--dry-run` to validate without submitting, and `--override <field>=<value>` (repeatable) to change a field without editing the YAML. |
| `databricks air get <JOB_RUN_ID>` | Show status, config, timing, and the failure reason for one run. |
| `databricks air list` | List your **active** runs. A run that just finished drops out of the default view; add `--all-status` to include finished runs. Also `--all-users`, `--filter KEY=VALUE`, `--limit`. |
| `databricks air cancel <JOB_RUN_ID> [<JOB_RUN_ID>...]` / `... --all` | Cancel one or more runs, or all of your active runs (`--all` prompts; add `--yes` in scripts). |
| `databricks air logs <JOB_RUN_ID>` | Stream a running run's logs, or fetch a finished run's logs. |
| `databricks air pools list` / `pools get <POOL_ID>` | View the provisioned GPU pools available to the workspace. |
| `databricks air images push` | Push a local or remote container image to Databricks Artifact Registry. See [docker-images.md](docker-images.md). |
| `databricks air convert-to-dabs <yaml_path>` | Convert a workload YAML into a Databricks Asset Bundle (local only; deploy with `databricks bundle deploy`). |

For flags and defaults, run `databricks air <subcommand> --help`.

## Workload YAML

```yaml
experiment_name: my-training-job     # alphanumeric, - and _ only
compute:
  num_accelerators: 1
  accelerator_type: GPU_1xA10        # run `databricks air run -h config.compute` for valid values
environment:
  version: "6"                       # Standard environment; use databricks_ai_v6 for PyTorch preinstalled
  dependencies:
    - torch
    - mlflow
code_source:
  root_path: "."                     # relative to workload.yaml; extracted to $CODE_SOURCE_PATH on each node
max_retries: 0                       # while iterating; see Retries below
command: |-
  cd "$CODE_SOURCE_PATH"
  python train.py
```

Submit with `databricks air run --file workload.yaml -p <profile>`. Field
details live in `databricks air run -h config.<field>` (the authoritative
source).

For an older CLI, replace only the `code_source` block above with:

```yaml
code_source:
  type: snapshot
  snapshot:
    root_path: "."
```

The values and behavior are the same: add `type: snapshot` under `code_source`
and put all snapshot fields (`root_path`, and any `remote_volume`, `git`, or
`include_paths`) inside `code_source.snapshot`. Keep the rest of the workload
unchanged. Check `databricks air run -h config.code_source` for the fields
supported by the installed CLI.

### Accelerator types

Run `databricks air run -h config.compute` to see the accelerator types. On CLI
1.23.0 and newer it lists the types **available in the current workspace** and
how many GPUs each type has per node; if it cannot reach the workspace, it
prints a warning and falls back to a built-in list. Do not guess a type from
memory: availability depends on the workspace, cloud, and region, and matching
is case-sensitive.

Type names follow `GPU_<GPUs per node>x<GPU>`, for example `GPU_1xA10`,
`GPU_1xH100`, `GPU_8xH100`, and `GPU_8xB300`. `num_accelerators` is the total
GPU count across all nodes, so it must be a multiple of the per-node count: 8
on an `8x` type is one node, 16 is two nodes. Only the `8x` types support
multi-GPU and multi-node training.

### Python environment

Pick the environment from what the training code imports, before you submit,
so a missing package does not surface only after a GPU has been provisioned:

| `environment` | What it provides | Use when |
|---|---|---|
| `version: "6"` (the default) | Standard environment: Python and CUDA only. Since version 5, it does **not** include `torch` or `torchvision`. | You control the dependency stack. List every import, including `torch`, under `dependencies`. |
| `version: databricks_ai_v6` | Databricks AI environment: PyTorch, Transformers, and other ML frameworks preinstalled. | Typical PyTorch or Hugging Face training. Add extras under `dependencies`. |
| `unity_catalog_image: <catalog>.<schema>.<image>:<tag>` | Your own Docker image. | System libraries or CUDA extensions; see [Custom Docker images](#custom-docker-images). |

Before submitting, check the script's imports against the chosen environment.
For the exact packages in each environment version, see the
[environment version release notes](https://docs.databricks.com/aws/en/release-notes/serverless/environment-version/).
Do not combine `unity_catalog_image` with `version` or `dependencies`.

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
hyperparameter without editing the YAML, resubmit with
`--override parameters.learning_rate=0.0005` (and a fresh idempotency key).

### Retries

Failed attempts are retried automatically: `max_retries` defaults to 3 when
unset (confirm with `databricks air run -h config.max_retries`). Each retry
provisions GPUs and reruns the whole command, so a deterministic failure (an
import error, a typo, a bad path) fails 4 times before the run gives up.

**Set `max_retries: 0` while writing, debugging, or iterating on a workload**,
either in the YAML or with `--override max_retries=0`. Raise it only for a
long, stable training run where retrying can recover from transient
infrastructure failures, and make the training code resume from a checkpoint
so a retry does not start over. When `timeout_minutes` is set, it applies
per attempt.

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

### Other fields

| Field | Use |
|---|---|
| `timeout_minutes` | Wall-clock limit per attempt, in minutes. |
| `idempotency_token` | YAML equivalent of `--idempotency-key`: resubmitting with the same token returns the existing run. |
| `mlflow_run_name`, `mlflow_experiment_directory` | Name the MLflow run, or choose the workspace directory that holds the experiment. |
| `compute.pool_id`, `compute.priority_class` | Run on a pre-provisioned GPU pool (find IDs with `databricks air pools list`). `priority_class` is `NORMAL` or `BEST_EFFORT` (preemptable) and requires `pool_id`. |
| `containers` | Run different images and commands on different node ranks, for example a trainer and an inference server. Replaces `command`; each entry needs `name`, `command`, `ranks`, and `unity_catalog_image`. See `databricks air run -h config.containers`. |

## Environment variables provided on each node

`databricks air` sets these automatically on every node; use them in `command:`
and in your training code.

| Variable | Meaning |
|---|---|
| `CODE_SOURCE_PATH` | Absolute path to your extracted `code_source` on the node (`cd $CODE_SOURCE_PATH`). |
| `MASTER_ADDR` / `MASTER_PORT` | Address/port of the rank-0 node for distributed coordination. |
| `NUM_NODES` | Total number of nodes. |
| `NODE_RANK` | Rank of the current node (0 to `NUM_NODES`-1). Also set as `POD_RANK`. |
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
   `$CODE_SOURCE_PATH`. **Total GPUs = nodes x accelerators-per-node**; see
   [Accelerator types](#accelerator-types).

3. **Pre-flight the referenced resources** so the job does not die on startup:
   - Every package the script imports is in the chosen
     [environment](#python-environment) or its `dependencies` (the Standard
     environment has no `torch`).
   - `max_retries: 0` is set while the workload is new or being debugged.
   - Every `secrets` scope/key exists (`databricks secrets list-scopes` /
     `list-secrets <scope>`).
   - If `environment.unity_catalog_image` is set, the image has been pushed to
     Databricks Artifact Registry in the same workspace and the submitting
     identity can read it (see [docker-images.md](docker-images.md)).

4. **Dry-run before submitting.** This validates the config without launching:
   ```bash
   databricks air run --file workload.yaml --dry-run -o json -p <profile>
   ```
   On CLI 1.20.0 and newer, the dry run also checks the config against the
   workspace, so it needs a working profile. A config-validation error is a
   hard stop: it prints as plain text on stderr with a non-zero exit, so show
   that message to the user and fix the YAML. Other failures are infra/auth
   and should bubble up.

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
databricks air get <JOB_RUN_ID> -o json -p <profile>        # status, config, timing, failure reason
databricks air list -o json -p <profile>                    # your active runs
databricks air list --all-status -o json -p <profile>       # include finished runs
```

`air get` reports `PENDING` while the run waits for GPUs, then `RUNNING`, then
a final state such as `SUCCESS` or `FAILED`. An empty `air list` means you have
no **active** runs, not that the run is gone; use `--all-status` or `air get`
to see a finished run.

## Monitoring a run

**Stream logs while it runs.** The simplest path is to submit with `--watch`,
which streams the run's logs to your terminal until it reaches a terminal state:

```bash
databricks air run --file workload.yaml --watch -p <profile>
```

For a run that is already going, stream its logs by ID:

```bash
databricks air logs <JOB_RUN_ID> -p <profile>
# --node N (one node), --tail N (last N lines of a finished run),
# --minutes N (last N minutes), --retry N (one retry attempt, 0-indexed),
# --download-to DIR (save all nodes' logs)
```

**Loss, GPU utilization, and metric history live in MLflow.** The CLI streams
logs and status, not training metrics. The submit/status response includes the
MLflow experiment and run URL; echo it so the user can open the run in the
Databricks UI for loss curves, GPU utilization, and system charts.

## If a run fails

Get the failure reason, then pull the logs and surface the actual error to the
user:

```bash
databricks air get <JOB_RUN_ID> -o json -p <profile>             # termination_reason
databricks air logs <JOB_RUN_ID> --tail 500 -p <profile>         # latest attempt
databricks air logs <JOB_RUN_ID> --retry 0 --tail 500 -p <profile>   # first attempt
```

If the run was retried, the latest attempt's logs may show a different symptom
than the first failure; check `--retry 0`. On a multi-node run, check other
nodes with `--node N` when node 0 looks healthy.

Show the failing traceback and let the user decide the fix. Before
resubmitting, set `max_retries: 0` so a deterministic error fails once. For a
deeper, guided diagnosis of a training failure, use AI Runtime's own debugging
support rather than guessing at root cause here.

## Custom Docker images

Use a custom Docker image instead of `environment.version` when your workload
needs specific system libraries, CUDA extensions (flash-attn, apex, custom
kernels), or dependencies that do not fit `environment.dependencies`.

**Read [docker-images.md](docker-images.md)** for step-by-step guidance on:

- Using Databricks-provided base images, including CUDA 13 images for B300
- Dockerfile patterns
- Pre-build compatibility checklist (CUDA/driver, PyTorch, NCCL, EFA/RDMA)
- Pushing images with `databricks air images push` and running them with
  `environment.unity_catalog_image`
- Troubleshooting runtime errors such as `ssl.SSLError` on FIPS hosts
