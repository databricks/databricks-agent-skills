---
name: databricks-ai-runtime
description: "Build custom Docker images for Databricks AI Runtime (`air`) CLI workloads. Use when the user needs to bring their own Docker container image to an `air` workload: writing Dockerfiles using Databricks base images or from scratch, navigating CUDA/NCCL/EFA compatibility, handling flash-attn CXX11 ABI pitfalls, and registering images with `air register image`."
compatibility: Requires databricks-air CLI
metadata:
  version: "0.1.0"
---

# Custom Docker images for Databricks AI Runtime

Build a custom Docker image when your training workload needs a CUDA
extension (flash-attn, apex, xformers, custom kernels), a non-standard
framework, or any system-level dependency that doesn't fit a plain
`pip install`. Reference the resulting image from the `air` YAML via
`environment.docker_image.url` and register it once with
`air register image` (see the last section).

Two paths:

1. **Databricks base images** (recommended) — CUDA, NCCL, and the
   correct AWS/Azure networking stack are pre-configured. You only
   add your ML framework and code.
2. **From scratch** — full control, but you install CUDA, NCCL, and
   the cloud-specific RDMA layer yourself.

---

## Option 1: Databricks base images

Published on Docker Hub at
[`databricksruntime/air`](https://hub.docker.com/r/databricksruntime/air/tags).

| Tag | Cloud | Variant | Size | Use |
|---|---|---|---|---|
| `dcs-base-aws-runtime` | AWS | Runtime | ~4.7 GB | `pip install` pre-built wheels only |
| `dcs-base-aws-devel` | AWS | Devel | ~11 GB | Compile CUDA extensions (needs `nvcc`) |
| `dcs-base-azure-runtime` | Azure | Runtime | ~4.1 GB | Pre-built wheels |
| `dcs-base-azure-devel` | Azure | Devel | ~10.3 GB | Compile CUDA extensions |

Pick **runtime** unless you need `nvcc` (e.g. for flash-attn, apex,
custom CUDA kernels). Expect ~10 GB final size after adding PyTorch
(runtime) or ~17 GB (devel).

### What's in all 4 variants

- Ubuntu 24.04, Python 3.12 in `/opt/venv`, managed by `uv` (`/usr/local/bin/uv`)
- CUDA 12.9.1 runtime, OS-level NCCL 2.27.3, `cuda-compat` for forward driver
  compatibility
- `OPENSSL_FORCE_FIPS_MODE=0` (Ubuntu 24.04 FIPS kernel workaround)
- `NVIDIA_VISIBLE_DEVICES=all`, `NVIDIA_DRIVER_CAPABILITIES=compute,utility`
- Devel adds: `nvcc`, CUDA headers, NCCL dev headers.
- AWS adds: EFA 1.42.0, libfabric, OpenMPI 4.1.7, aws-ofi-nccl 1.15.0,
  `FI_EFA_USE_DEVICE_RDMA=1`, `LD_LIBRARY_PATH` + `PATH` pre-set.
- Azure adds: `rdma-core` 50.0, `ibverbs-utils`, `infiniband-diags`,
  `perftest`, `libibverbs-dev`, `librdmacm-dev`.

> **OS-level NCCL is usually unused.** A `pip install torch` wheel ships
> its own bundled NCCL (e.g. torch 2.6 → NCCL 2.21.5) and loads it
> preferentially over `/usr/lib/.../libnccl.so`. The `2.27.3` above is
> what's on disk, not what your job actually links against. Verify:
> `python3 -c "import torch; print(torch.cuda.nccl.version())"`.

### Deriving a PyTorch image

```dockerfile
FROM databricksruntime/air:dcs-base-aws-runtime

RUN uv pip install --no-cache \
    torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0

COPY requirements.txt /tmp/requirements.txt
RUN uv pip install --no-cache \
    -r /tmp/requirements.txt

COPY . /app
```

`requirements.txt` should not re-list `torch` / `torchvision`. Swap the
tag to `-azure` on Azure; swap to `-devel-*` if you need `nvcc`.

---

## Option 2: From scratch

> **Driver check before you start.** Pick a CUDA toolkit the host
> driver already supports — don't install `cuda-compat` reflexively.
>
> | Cloud | Host node image | Driver |
> |---|---|---|
> | AWS | Amazon Linux 2023 | `580.126.16` |
> | Azure | Azure Linux | `580.105.08` |
>
> Both 580.x drivers natively support every CUDA 12.x toolkit and CUDA
> 13.0 with **no** `cuda-compat` layer. Installing or LD-prioritizing
> `cuda-compat` on a 580.x host downgrades the userspace `libcuda`
> below the kernel driver and triggers Error 803 — see §2 "CUDA toolkit
> vs driver" below.
>
> Verify the live driver from any running pod before you commit to a
> CUDA version:
> ```bash
> nvidia-smi --query-gpu=driver_version --format=csv,noheader
> ```
> If you see something below 580.x (rare; older Ubuntu pools were on
> the 550 line), pin your CUDA toolkit to ≤ 12.4 or install
> `cuda-compat-12-X` for the toolkit you want.

Pick a base image:

- `nvidia/cuda:12.9.0-runtime-ubuntu24.04` — runtime only
- `nvidia/cuda:12.9.0-devel-ubuntu24.04` — includes `nvcc`, headers
- Or your own base image (corporate image, different OS/CUDA)

The steps below assume Ubuntu 24.04 + CUDA 12.9. If you start from a
different OS or CUDA version, package names, paths, and versions may
differ — and you're responsible for ensuring CUDA runtime + NCCL are
present in the final image.

### System setup

```dockerfile
FROM nvidia/cuda:12.9.0-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV OPENSSL_FORCE_FIPS_MODE=0

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv python3-dev \
    ca-certificates curl git wget openssh-client iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Databricks expects Python at this path
RUN mkdir -p /databricks/python/bin && \
    ln -sf /usr/bin/python3 /databricks/python/bin/python

ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility
```

### AWS networking (EFA)

EFA is needed for multi-node GPU communication **only on instance
families with EFA hardware** — `GPU_8xH100` (P5-class) today.
For `GPU_1xA10` (A10/G-family, single GPU per pod), EFA is not
present on the host; installing it just bloats the image (~600 MB) and
NCCL logs three OFI WARN lines per job before falling back to socket
transport. Skip this whole section for A10-only workloads.

If you do need EFA, the installer bundles libfabric, OpenMPI, and the
`aws-ofi-nccl` NCCL plugin:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    hwloc libhwloc-dev \
    && rm -rf /var/lib/apt/lists/*

ARG EFA_VERSION=1.42.0
RUN cd /tmp && \
    curl -fsSL --retry 5 --retry-delay 5 --retry-max-time 300 --retry-all-errors \
      https://s3-us-west-2.amazonaws.com/aws-efa-installer/aws-efa-installer-${EFA_VERSION}.tar.gz \
      -o aws-efa-installer.tar.gz && \
    tar xzf aws-efa-installer.tar.gz && cd aws-efa-installer && \
    apt-get update && \
    ./efa_installer.sh -y --skip-kmod --skip-limit-conf --no-verify && \
    rm -rf /var/lib/apt/lists/* && \
    cd /tmp && rm -rf aws-efa-installer aws-efa-installer.tar.gz

# libfabric needs unversioned libcudart.so for GPU-direct RDMA (FI_HMEM_CUDA)
RUN ln -sf libcudart.so.12 /usr/local/cuda/lib64/libcudart.so

ENV LD_LIBRARY_PATH=/opt/amazon/ofi-nccl/lib/x86_64-linux-gnu:/opt/amazon/openmpi/lib:/opt/amazon/efa/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}
ENV PATH=/opt/amazon/openmpi/bin:/opt/amazon/efa/bin${PATH:+:${PATH}}
ENV FI_EFA_USE_DEVICE_RDMA=1
```

`-f` fails fast on HTTP errors; `--retry-all-errors` covers partial
transfers (`curl 18`) that the default retry policy ignores. If the
build can't reach S3 at all, pre-download the tarball on the host and
`COPY` it instead.

> **Base images install EFA unconditionally** too. If you start from
> Option 1 and your `gpu_type` is `a10`, the OFI plugin will still try to
> probe at NCCL init and emit three `NET/OFI ... initialization failed`
> WARN lines per job. They're non-fatal (NCCL falls back to socket); to
> silence: `env_variables: { NCCL_NET_PLUGIN: "none" }` in the `air` YAML.

### Azure networking (InfiniBand)

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    rdma-core ibverbs-utils infiniband-diags perftest \
    libibverbs-dev librdmacm-dev \
    && rm -rf /var/lib/apt/lists/*
```

### ML framework and code

```dockerfile
RUN python3 -m pip install --no-cache-dir --break-system-packages \
    torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0

COPY . /app
```

Reference the code in your `air` `command:` via absolute path
(`python /app/train.py`) — see the WORKDIR note below.

---

## flash-attn and CXX11 ABI (the gotcha)

The base images ship without PyTorch, so the torch wheel you install
determines a `_GLIBCXX_USE_CXX11_ABI` flag that every CUDA extension in
the image must match. Mismatch → `ImportError: undefined symbol:
_ZN3c105Error...` at runtime.

Find your torch's ABI after installing:

```bash
python3 -c "import torch; print(torch._C._GLIBCXX_USE_CXX11_ABI)"
```

Two upstream pitfalls:

- **flash-attn v2.8.0+ wheels are mislabeled.** GitHub release wheels
  tagged `cxx11abiFALSE` are actually built with ABI=True. The
  `FALSE`-labeled wheel fails to load on old-ABI torch.
- **Source builds ignore torch's ABI.** `pip install flash-attn
  --no-build-isolation` on Ubuntu 24.04 always produces new-ABI
  regardless of torch.

**Recommended:** pin `flash-attn==2.7.4.post1` — the last release where
the ABI labels match the build. Pre-download on the host, `COPY`
into the image, install with `--no-deps`:

```dockerfile
FROM databricksruntime/air:dcs-base-aws-runtime

RUN uv pip install --no-cache \
    torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0

# curl the wheel + `pip download einops==0.8.2 --no-deps` on host first
COPY flash_attn-2.7.4.post1+cu12torch2.6cxx11abiFALSE-cp312-cp312-linux_x86_64.whl /tmp/
COPY einops-0.8.2-py3-none-any.whl /tmp/
RUN uv pip install --no-cache --no-deps \
    /tmp/einops-0.8.2-py3-none-any.whl \
    /tmp/flash_attn-2.7.4.post1+cu12torch2.6cxx11abiFALSE-cp312-cp312-linux_x86_64.whl \
    && rm /tmp/*.whl
```

flash-attn source builds need `nvcc` → use a `devel` base image.

---

## WORKDIR is not honored at runtime

AI Runtime does not respect the Docker `WORKDIR` directive.
Your command runs from a platform-controlled directory, not your
image's `WORKDIR`. **Use absolute paths** for anything baked into the
image.

```yaml
# WRONG — "No such file"
command: |-
  python train.py

# CORRECT
command: |-
  python /app/train.py
```

Use `COPY . /app` in the Dockerfile and reference `/app/<file>` in the
`air` YAML.

---

## Pre-build compatibility check

Walk through these checks before building. If anything fails, fix the
Dockerfile first — most failures only surface at job runtime, hours
after the build.

### 1. Host GPU driver

Run on any pod (a 1-GPU `air run` is enough) — `nvidia-smi` is the
only ground truth:

```bash
nvidia-smi --query-gpu=driver_version --format=csv,noheader
```

Today's expected values:

| Cloud | Driver | CUDA toolkits supported natively |
|---|---|---|
| AWS (Amazon Linux 2023) | `580.126.16` | 12.x and 13.0 |
| Azure (Azure Linux) | `580.105.08` | 12.x and 13.0 |

If you see anything below the 580 line, jump to §2.

### 2. CUDA toolkit vs driver

CUDA toolkits enforce a minimum driver version on Linux:

| Container CUDA toolkit | Min driver | 550.x host | 580.x host |
|---|---|---|---|
| 12.4.x | 550.54.14 | ✅ | ✅ |
| 12.6.x | 560.28.03 | ❌ needs `cuda-compat-12-6` | ✅ |
| 12.8.x | 570.86.15 | ❌ needs `cuda-compat-12-8` | ✅ |
| 12.9.x | 570.86.15 | ❌ needs `cuda-compat-12-9` | ✅ |
| 13.0.x | 580.65.06 | ❌ pin a lower toolkit | ✅ |

Two rules:

- **Driver ≥ minimum** (the common case on 580.x): **do not install or
  LD-prioritize `cuda-compat`.** It ships a userspace `libcuda`
  matching the *minimum* driver for that CUDA version, so forcing it
  onto the load path with a newer kernel driver creates a backwards
  mismatch — Error 803, "system has unsupported display driver / cuda
  driver combination", and NCCL reports "no GPUs found" even though
  `nvidia-smi` works.
- **Driver < minimum** (only seen on legacy 550.x pools today): either
  pin a lower CUDA toolkit, or `apt-get install
  cuda-compat-<major>-<minor>` and ensure it's first on
  `LD_LIBRARY_PATH`. Databricks base images already include
  `cuda-compat` for this case so they work on either driver line.

### 3. PyTorch vs CUDA

| PyTorch | Default wheel | Compatible CUDA |
|---|---|---|
| 2.6.x | cu124 | 12.4+ (works on 12.9 via minor compat) |
| 2.7.x | cu126 | 12.6+ |
| 2.5.x | cu124 | 12.4+ |

`pip install torch==2.6.0` gives cu124, not cu126 — still works on
CUDA 12.9. `pip install torch==2.7.*` defaults to cu126.

Verify after build: `python3 -c "import torch; print(torch.version.cuda)"`.

### 4. NCCL

`pip install torch` ships its own NCCL bundled inside the wheel
(`torch/lib/libnccl.so.*`) and loads it preferentially over anything in
`/usr/lib`. The OS-level NCCL listed in package lists is typically
**not** what your job actually links against. Verify after build:

```bash
docker run --rm <your-image> python3 -c \
  "import torch; print('runtime NCCL:', torch.cuda.nccl.version())"
```

You only need to align OS-level NCCL with the CUDA major version when
the user is overriding NCCL or installing a standalone copy
(`LD_PRELOAD`, custom `libnccl.so` builds, etc.).

### 5. CXX11 ABI (CUDA extensions)

If the Dockerfile installs anything that compiles or links against
CUDA extensions (flash-attn, apex, xformers, custom kernels), confirm
the extension's ABI matches the installed torch. See the flash-attn
section above for the specific pitfall.

Check after build:

```bash
docker run --rm <your-image> python3 -c \
  "import torch; print('torch CXX11 ABI:', torch._C._GLIBCXX_USE_CXX11_ABI)"
```

### 6. EFA / RDMA

- **AWS EFA:** the Databricks base images ship EFA 1.42.0. For
  scratch builds, target the same version on EFA-capable instance
  families (H100 / P5-class) and skip EFA entirely on A10 / G-family.
- **Azure RDMA:** `rdma-core` from Ubuntu apt works.

### Summary table

```
## Compatibility Check

| Check                        | Status      | Details |
|------------------------------|-------------|---------|
| CUDA toolkit vs host driver  | OK/WARN     | CUDA X needs ≥Y; host Z. cuda-compat: needed / NOT needed (host already ≥ minimum) |
| PyTorch vs CUDA              | OK/FAIL     | torch A.B ships cuXYZ, image has CUDA X.Y |
| NCCL                         | OK/N/A      | torch-bundled NCCL loads preferentially; OS NCCL usually unused |
| EFA/RDMA                     | OK/WARN/N/A | EFA X.Y.Z vs node image (N/A on a10 — non-EFA hardware) |
| CXX11 ABI (CUDA extensions)  | OK/WARN/N/A | extension ABI matches torch ABI |
```

FAIL → stop and fix the Dockerfile. WARN → understand the risk and
decide whether it applies to your workload.

---

## Register and run

Custom images must be **registered** before `air` can run them
(one-time per image SHA; the platform pulls and caches it).

```bash
air register image <registry>/<repo>:<tag> -p <profile>
# Private registry, credentials stored in a Databricks secret (recommended):
air register image <registry>/<repo>:<tag> -p <profile> --scope <scope> --key <key>
# Private registry, prompt for credentials interactively at the terminal:
air register image <registry>/<repo>:<tag> -p <profile> --interactive-authenticate
```

Registration takes 2–6 min and blocks until the image is ready.

> Prefer the `--scope <scope> --key <key>` form for any automated /
> non-interactive flow (CI, scripts) — `--interactive-authenticate`
> reads credentials from the controlling TTY and will hang in
> environments without one.

Reference in the `air` YAML:

```yaml
experiment_name: my-training-job
compute:
  num_accelerators: 1
  accelerator_type: GPU_1xA10
environment:
  docker_image:
    url: <registry>/<repo>:<tag>
command: |-
  python /app/train.py --epochs 5
```

Use absolute paths in `command:` — see the WORKDIR section above.
