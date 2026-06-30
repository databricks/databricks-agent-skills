---
name: databricks-ai-runtime
description: "Databricks AI Runtime (`air`) CLI — the command-line tool for submitting and managing GPU training workloads on Databricks serverless compute. Use for: running `air` workloads, custom Docker image setup, environment configuration, and troubleshooting `air` jobs."
compatibility: Requires databricks-air CLI. See the [installation guide](https://docs.databricks.com/aws/en/machine-learning/ai-runtime/cli/installation) to get started.
metadata:
  version: "0.1.0"
---

# Databricks AI Runtime (`air`) CLI

Databricks AI Runtime (`air`) is a CLI tool for submitting GPU training workloads to Databricks serverless compute. It manages environment setup, distributed training configuration, and workload lifecycle — without requiring you to manage clusters or infrastructure.

A typical workload YAML looks like:

```yaml
experiment_name: my-training-job
compute:
  num_accelerators: 1
  accelerator_type: GPU_1xA10
environment:
  dependencies:
    - mlflow
  version: "AI5"
command: echo "Hello World"
```

Submit with `air run --file workload.yaml -p <databricks_config_profile>`.

## Bring your own custom Docker images

Use a custom Docker image instead of `environment.version` when your workload needs specific system libraries, CUDA extensions (flash-attn, apex, custom kernels), or dependencies that don't fit `environment.dependencies`.

**Read [docker-images.md](docker-images.md)** for step-by-step guidance on:

- Using Databricks-provided base images
- Dockerfile patterns
- Pre-build compatibility checklist (CUDA/driver, PyTorch, NCCL, EFA/RDMA)
- Registering images with `air register image`
