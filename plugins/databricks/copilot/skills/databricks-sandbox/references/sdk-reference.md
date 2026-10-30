# Databricks Sandbox SDK - Reference

Methods on `w.sandbox` (the `Sandbox` client on `WorkspaceClient`).

**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sandbox/sandbox.html
**Streaming Command execution:** https://databricks-sdk-py.readthedocs.io/en/latest/sandbox-command-execution.html

A sandbox's resource `name` is `sandboxes/<sandbox_id>`.

## Lifecycle

| Method | Signature |
|--------|-----------|
| `create_sandbox` | `(sandbox: Sandbox, sandbox_id: str) -> Sandbox` |
| `get_sandbox` | `(name: str) -> Sandbox` |
| `list_sandboxes` | `([page_size: int], [page_token: str]) -> Iterator[Sandbox]` |
| `start_sandbox` | `(name: str) -> Sandbox` |
| `stop_sandbox` | `(name: str) -> Sandbox` |
| `delete_sandbox` | `(name: str) -> None` |
| `update_sandbox` | `(name: str, sandbox: Sandbox, update_mask: FieldMask) -> Sandbox` |

## Command Execution

| Method | Signature |
|--------|-----------|
| `execute_command_sync` | `(name: str, cmd: str, [args: list[str]], [envs: dict[str, str]], [execution_timeout: Duration]) -> ExecuteCommandSyncResponse` |
| `execute_command` | `(name: str, cmd: str, *, [args: list[str]], [envs: dict[str, str]], text: bool = True, stdout: StreamMode = PIPE, stderr: StreamMode = PIPE) -> CommandProcess` |
| `connect_command` | `(name: str, command_id: str, *, text: bool = True, stdout: StreamMode = PIPE, stderr: StreamMode = PIPE) -> CommandProcess` |
| `list_commands` | `(parent: str, [page_size: int], [page_token: str]) -> ListCommandsResponse` |

`cmd` runs directly, not in a shell. Use `/bin/bash` with `args=["-c", "..."]` for shell features.

**`ExecuteCommandSyncResponse`** fields: `command_id`, `exit_code`, `status`, `stdout`, `stderr`, `truncated`.

**`CommandProcess`** (streaming handle):
- Attributes: `stdout` (iterable output stream), `stderr` (iterable output stream), `stdin`, `command_id`, `pid`, `exit_code`.
- Methods: `wait(timeout: float | None = None) -> int` (block for exit code), `close()` (release the stream). Supports the context-manager protocol (`with ... as proc:`).

**`StreamMode`** enum: `PIPE` (buffer in memory for reading), `DEVNULL` (discard), `STDOUT` (stderr-only; merge stderr into stdout).

## File System

All take `parent` (the sandbox `name`) plus a path.

| Method | Signature |
|--------|-----------|
| `create_directory` | `(parent: str, path: str, [parents: bool]) -> CreateDirectoryResponse` |
| `list_directory_contents` | `(parent: str, path: str, [page_size: int], [page_token: str]) -> Iterator[SandboxFileInfo]` |
| `get_metadata` | `(parent: str, path: str) -> GetMetadataResponse` |
| `rename_path` | `(parent: str, source: str, destination: str) -> RenamePathResponse` |
| `delete_path` | `(parent: str, path: str, [recursive: bool]) -> DeletePathResponse` |
