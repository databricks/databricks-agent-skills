"""Memory tools for LangGraph agents.

This module provides tools for managing user long-term memory using
Databricks Lakebase. Copy this file to your agent_server/ directory.

Usage:
    from agent_server.memory_tools import memory_tools, get_user_id

    # In your streaming function:
    user_id = get_user_id(request)
    tools = await mcp_client.get_tools() + memory_tools()
    config = {"configurable": {"user_id": user_id, "store": store}}
"""

import json
import logging
import os
from typing import Optional

from databricks.sdk import WorkspaceClient
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.store.base import BaseStore
from mlflow.types.responses import ResponsesAgentRequest


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------


def get_user_id(request: ResponsesAgentRequest) -> Optional[str]:
    """Extract user_id from request context or custom inputs.

    Checks custom_inputs first (for API calls), then request.context
    (for Databricks Apps with OBO authentication).

    Returns None if no user_id found - let the caller decide the fallback.
    """
    custom_inputs = dict(request.custom_inputs or {})
    if "user_id" in custom_inputs:
        return custom_inputs["user_id"]
    if request.context and getattr(request.context, "user_id", None):
        return request.context.user_id
    return None


def _is_lakebase_hostname(value: str) -> bool:
    """Check if the value looks like a Lakebase hostname rather than an instance name."""
    return ".database." in value and value.endswith(".com")


def resolve_lakebase_instance_name(
    instance_name: str, workspace_client: Optional[WorkspaceClient] = None
) -> str:
    """Resolve a Lakebase instance name from a hostname if needed.

    If the input is a hostname (e.g., from Databricks Apps value_from resolution),
    this will resolve it to the actual instance name by listing database instances.

    Args:
        instance_name: Either an instance name or a hostname
        workspace_client: Optional WorkspaceClient to use for resolution

    Returns:
        The resolved instance name

    Raises:
        ValueError: If the hostname cannot be resolved to an instance name
    """
    if not _is_lakebase_hostname(instance_name):
        return instance_name

    client = workspace_client or WorkspaceClient()
    hostname = instance_name

    try:
        instances = list(client.database.list_database_instances())
    except Exception as exc:
        raise ValueError(
            f"Unable to list database instances to resolve hostname '{hostname}'. "
            "Ensure you have access to database instances."
        ) from exc

    for instance in instances:
        rw_dns = getattr(instance, "read_write_dns", None)
        ro_dns = getattr(instance, "read_only_dns", None)

        if hostname in (rw_dns, ro_dns):
            resolved_name = getattr(instance, "name", None)
            if not resolved_name:
                raise ValueError(
                    f"Found matching instance for hostname '{hostname}' "
                    "but instance name is not available."
                )
            logging.info(f"Resolved Lakebase hostname '{hostname}' to instance name '{resolved_name}'")
            return resolved_name

    raise ValueError(
        f"Unable to find database instance matching hostname '{hostname}'. "
        "Ensure the hostname is correct and the instance exists."
    )


def _is_databricks_app_env() -> bool:
    """Check if running in a Databricks App environment."""
    return bool(os.getenv("DATABRICKS_APP_NAME"))


def get_lakebase_access_error_message(lakebase_instance_name: str) -> str:
    """Generate a helpful error message for Lakebase access issues."""
    if _is_databricks_app_env():
        app_name = os.getenv("DATABRICKS_APP_NAME")
        return (
            f"Failed to connect to Lakebase instance '{lakebase_instance_name}'. "
            f"The App Service Principal for '{app_name}' may not have access.\n\n"
            "To fix this:\n"
            "1. Go to the Databricks UI and navigate to your app\n"
            "2. Click 'Edit' → 'App resources' → 'Add resource'\n"
            "3. Add your Lakebase instance as a resource\n"
            "4. Grant the necessary permissions on your Lakebase instance."
        )
    else:
        return (
            f"Failed to connect to Lakebase instance '{lakebase_instance_name}'. "
            "Please verify:\n"
            "1. The instance name is correct\n"
            "2. You have the necessary permissions to access the instance\n"
            "3. Your Databricks authentication is configured correctly"
        )


# -----------------------------------------------------------------------------
# Memory Tools Factory
# -----------------------------------------------------------------------------


def memory_tools():
    """Factory function returning memory tools for the agent.

    Returns a list of tools that can be added to your agent:
    - get_user_memory: Search for relevant information from long-term memory
    - save_user_memory: Save information to long-term memory
    - delete_user_memory: Delete a specific memory

    Usage:
        tools = await mcp_client.get_tools() + memory_tools()
        config = {"configurable": {"user_id": user_id, "store": store}}
    """

    @tool
    async def get_user_memory(query: str, config: RunnableConfig) -> str:
        """Search for relevant information about the user from long-term memory.

        Use this to recall preferences, past interactions, or other saved information.

        Args:
            query: What to search for in the user's memories
        """
        user_id = config.get("configurable", {}).get("user_id")
        if not user_id:
            return "Memory not available - no user_id provided."

        store: Optional[BaseStore] = config.get("configurable", {}).get("store")
        if not store:
            return "Memory not available - store not configured."

        namespace = ("user_memories", user_id.replace(".", "-"))
        results = await store.asearch(namespace, query=query, limit=5)

        if not results:
            return "No memories found for this user."

        memory_items = [f"- [{item.key}]: {json.dumps(item.value)}" for item in results]
        return f"Found {len(results)} relevant memories:\n" + "\n".join(memory_items)

    @tool
    async def save_user_memory(memory_key: str, memory_data_json: str, config: RunnableConfig) -> str:
        """Save information about the user to long-term memory.

        Use this to remember user preferences, important details, or other
        information that should persist across conversations.

        Args:
            memory_key: A short descriptive key (e.g., "preferred_name", "team", "interests")
            memory_data_json: JSON object to save (e.g., '{"value": "engineering"}')
        """
        user_id = config.get("configurable", {}).get("user_id")
        if not user_id:
            return "Cannot save memory - no user_id provided."

        store: Optional[BaseStore] = config.get("configurable", {}).get("store")
        if not store:
            return "Cannot save memory - store not configured."

        namespace = ("user_memories", user_id.replace(".", "-"))

        try:
            memory_data = json.loads(memory_data_json)
            if not isinstance(memory_data, dict):
                return f"Failed: memory_data must be a JSON object, not {type(memory_data).__name__}"
            await store.aput(namespace, memory_key, memory_data)
            return f"Successfully saved memory '{memory_key}' for user."
        except json.JSONDecodeError as e:
            return f"Failed to save memory: Invalid JSON - {e}"

    @tool
    async def delete_user_memory(memory_key: str, config: RunnableConfig) -> str:
        """Delete a specific memory from the user's long-term memory.

        Use this when the user asks to forget something or correct stored information.

        Args:
            memory_key: The key of the memory to delete (e.g., "preferred_name", "team")
        """
        user_id = config.get("configurable", {}).get("user_id")
        if not user_id:
            return "Cannot delete memory - no user_id provided."

        store: Optional[BaseStore] = config.get("configurable", {}).get("store")
        if not store:
            return "Cannot delete memory - store not configured."

        namespace = ("user_memories", user_id.replace(".", "-"))
        await store.adelete(namespace, memory_key)
        return f"Successfully deleted memory '{memory_key}' for user."

    return [get_user_memory, save_user_memory, delete_user_memory]
