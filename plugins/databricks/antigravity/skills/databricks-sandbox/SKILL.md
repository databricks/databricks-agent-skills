---
name: databricks-sandbox
description: "Databricks Sandbox: on-demand serverless compute for running untrusted or agent-generated code and background tasks. Create/start/stop/delete sandboxes, run commands (synchronous execute_command_sync in all SDKs; streaming execute_command in the Python SDK only), and manage files through the Databricks SDK (Python, Java, Go, JavaScript). Use for Databricks Sandbox, serverless code-execution environments, or coding-agent runtimes."
compatibility: Requires databricks-sdk >= 0.154.0 (Python); the [sandbox] extra is only needed for streaming execute_command
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Databricks Sandbox

Databricks Sandbox is a serverless, isolated compute environment for humans and agents to run untrusted code. Drive it from code with the **Databricks SDK**, available in Python, Java, Go, and JavaScript. Lifecycle, file operations, and synchronous `execute_command_sync` are available in all four SDKs; streaming `execute_command` is currently Python-only. The examples in this skill use the Python SDK.

**SDK reference (Python):** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sandbox/sandbox.html
**Product docs:** https://docs.databricks.com/compute/serverless/sandbox
**SDK user guide:** https://docs.databricks.com/compute/serverless/sandbox-usage-guide
**REST API reference:** https://docs.databricks.com/api/sandbox/v1/sandbox

Other language SDKs: [Java](https://javadoc.io/doc/com.databricks/databricks-sdk-java/latest/index.html), [Go](https://pkg.go.dev/github.com/databricks/databricks-sdk-go/service/sandbox), [JavaScript](https://www.npmjs.com/package/@databricks/sdk-sandbox?activeTab=versions).

For the full per-method signature table, see [references/sdk-reference.md](references/sdk-reference.md).

## Environment Setup

- Install the SDK with the sandbox extra: `uv pip install "databricks-sdk[sandbox]>=0.154.0"`. The `sandbox` extra supplies the gRPC dependencies that streaming `execute_command` needs (the plain `databricks-sdk` package omits them); lifecycle, file operations, and unary `execute_command_sync` work without the extra. 0.154.0 is the first release with the file-operation methods used below.
- Authentication, profiles, and `~/.databrickscfg` are covered by the `databricks-core` skill. The sandbox client authenticates like any other `WorkspaceClient`.
- Your workspace must be in a supported region (see [Features with limited regional availability](https://docs.databricks.com/resources/feature-region-support#serverless-availability)) and have the **Databricks Sandbox** preview enabled on the workspace Previews page.

## Resource Naming

A sandbox's resource `name` is `sandboxes/<sandbox_id>`. `create_sandbox` takes the bare `sandbox_id`; every other call takes the full `name`.

## Lifecycle

Lifecycle calls return before the transition finishes (`create_sandbox` returns while `PENDING`, `stop_sandbox` while `STOPPING`), so poll `get_sandbox(name).status.state` and wait for the target state before depending on it.

```python
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sandbox import ComputeSpec, Sandbox, SandboxSpec, SandboxState
from google.protobuf.duration_pb2 import Duration

w = WorkspaceClient()

def wait_for_state(name: str, state: SandboxState, timeout: float = 300) -> Sandbox:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        sandbox = w.sandbox.get_sandbox(name=name)
        if sandbox.status and sandbox.status.state == state:
            return sandbox
        time.sleep(2)
    raise TimeoutError(f"{name} did not reach {state}")

# Create returns while the sandbox is still PENDING; wait for RUNNING before use.
# A sandbox bills hourly while running; set inactivity_timeout so it auto-stops when
# idle.
# Sandboxes can be updated with update_sandbox. The only accepted update paths
# are display_name and spec.compute.inactivity_timeout.
created = w.sandbox.create_sandbox(
    sandbox=Sandbox(spec=SandboxSpec(compute=ComputeSpec(inactivity_timeout=Duration(seconds=3600)))),
    sandbox_id="my-sandbox",
)
name = created.name  # "sandboxes/my-sandbox"
wait_for_state(name, SandboxState.SANDBOX_STATE_RUNNING)

# Inspect
sandbox = w.sandbox.get_sandbox(name=name)
for s in w.sandbox.list_sandboxes():
    print(s.name)

# Stop keeps the home directory; it returns while STOPPING, so wait for STOPPED
# before starting again.
w.sandbox.stop_sandbox(name=name)
wait_for_state(name, SandboxState.SANDBOX_STATE_STOPPED)
w.sandbox.start_sandbox(name=name)
wait_for_state(name, SandboxState.SANDBOX_STATE_RUNNING)

# Delete is terminal.
w.sandbox.delete_sandbox(name=name)
```

Stopping preserves only the home directory (`/home/sandbox-agent`, which holds up to 100 GB); data written elsewhere does not survive a stop (up to 10 GB of non-home storage, cleared on stop). Deleting a sandbox is terminal.

A stopped sandbox (previously by `stop_sandbox()`) can be restarted by explicit `start_sandbox()` or by running `execute_command` / `execute_command_sync` against the sandbox. For sandbox creation or restart through `create_sandbox()` and `start_sandbox()`, wait for the sandbox status to reach Running before using it; `execute_command` / `execute_command_sync` auto-starts a stopped sandbox and wait for it to reach Running, and no sandbox status polling is required.

## Running Commands

Pick the mode by workload:

| Mode | Method | Use for |
|------|--------|---------|
| Synchronous | `execute_command_sync` | Short commands where you only need the final stdout/stderr/exit code |
| Streaming | `execute_command` | Long-running or interactive commands where you consume output as it is produced |

Streaming `execute_command` (the `CommandProcess` handle) is currently available only in the Python SDK; `execute_command_sync` is available in all SDKs.

`cmd` runs directly (not through a shell), so to use shell features invoke `/bin/bash -c "..."` explicitly via `args`.

### Synchronous

```python
from google.protobuf.duration_pb2 import Duration

resp = w.sandbox.execute_command_sync(
    "sandboxes/my-sandbox",
    "/bin/bash",
    args=["-c", "echo hello && whoami"],
    execution_timeout=Duration(seconds=30),
)
print(resp.status, resp.exit_code, resp.truncated, resp.stdout, resp.stderr)
# Check resp.status for the terminal status: exit_code is unset when the command is
# killed (e.g. timed out) or fails to start. resp.truncated is True when the output
# hit the sync size cap - use execute_command (streaming) for large output.
```

### Streaming

`execute_command` returns a `CommandProcess` handle once the command has started. Iterate `stdout` / `stderr` for live output and call `wait()` for the exit code; use it as a context manager to release the client-side stream and reader thread on exit. Closing the handle (or leaving the `with` block) tears down the client side only - the command keeps running in the sandbox. There is no per-command cancel API; to actually stop it, read its server-side PID from `proc.pid` and kill it with a separate command, e.g. `w.sandbox.execute_command_sync(name, "/bin/kill", args=[str(proc.pid)])`.

```python
with w.sandbox.execute_command(
    "sandboxes/my-sandbox",
    "/bin/bash",
    args=["-c", "for i in 1 2 3; do echo line $i; sleep 1; done"],
) as proc:
    for line in proc.stdout:
        print(line, end="")
    exit_code = proc.wait()  # also available as proc.exit_code once finished
```

`stdout` / `stderr` default to `StreamMode.PIPE` (buffered for reading); pass `StreamMode.DEVNULL` to discard, or `StreamMode.STDOUT` on `stderr` to merge it into stdout. Pass `text=False` for `bytes` instead of decoded `str`. Reattach to a still-running command with `connect_command(name, command_id)`, and review history with `list_commands(parent="sandboxes/my-sandbox")`.

## Files

Manage the sandbox filesystem without a shell. All methods take `parent` (the sandbox `name`) plus a `path`. Write under the sandbox user's home directory, `/home/sandbox-agent` (the only persisted, writable tree; `/home` itself is root-owned, and paths outside the home directory are cleared on stop).

```python
w.sandbox.create_directory(parent="sandboxes/my-sandbox", path="/home/sandbox-agent/data", parents=True)
for entry in w.sandbox.list_directory_contents(parent="sandboxes/my-sandbox", path="/home/sandbox-agent/data"):
    print(entry.path)
w.sandbox.get_metadata(parent="sandboxes/my-sandbox", path="/home/sandbox-agent/data")
w.sandbox.rename_path(parent="sandboxes/my-sandbox", source="/home/sandbox-agent/a", destination="/home/sandbox-agent/b")
w.sandbox.delete_path(parent="sandboxes/my-sandbox", path="/home/sandbox-agent/b", recursive=True)
```

Use the sandbox `execute_command` APIs to move data in and out; native API/SDK support for uploading and downloading file contents (local <-> sandbox) is not yet available.

## When to Use

- **Agent / untrusted code execution** - run model-generated code off the host, in isolation.
- **Ephemeral build/test environments** - create, use, delete.
