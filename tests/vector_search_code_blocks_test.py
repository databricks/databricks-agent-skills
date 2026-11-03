#!/usr/bin/env python3
"""Guards the databricks-vector-search skill's Python examples against client misuse that fails only at runtime.

Requires Python 3.9+ (ast.unparse); CI runs 3.11.
"""
import ast
import re
import textwrap
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SKILL_DIR = _REPO / "skills" / "databricks-vector-search"
# Fences can be indented (inside list items), use ``` or ~~~, and carry attributes after the language tag.
_PYTHON_FENCE = re.compile(r"^[ \t]*(```|~~~)(?:python3?|py)\b[^\n]*\n(.*?)^[ \t]*\1[ \t]*$", re.S | re.M | re.I)
_SDK_SERVICES = {"vector_search_endpoints", "vector_search_indexes"}
_AI_SEARCH_CREATE_METHODS = {
    "create_endpoint",
    "create_endpoint_and_wait",
    "create_delta_sync_index",
    "create_delta_sync_index_and_wait",
    "create_direct_access_index",
}
# databricks.sdk.service.serving.ChatMessage is a dataclass with fields (content, role), so role is the 2nd positional arg.
_CHAT_MESSAGE_ROLE_POSITION = 1
_SDK_SERVING_MODULE = "databricks.sdk.service.serving"
_NONEXISTENT_HELPERS = re.compile(r"\b(manage_vs_endpoint|manage_vs_index|query_vs_index)\b")
# A few below the real count, so dropping a handful of examples (or the whole skill moving off
# AISearchClient) fails here instead of silently leaving the AST checks with nothing to inspect.
_MIN_AI_SEARCH_CREATE_CALLS = 12


def _markdown_files():
    return sorted(_SKILL_DIR.rglob("*.md"))


def _blocks_in(text):
    for match in _PYTHON_FENCE.finditer(text):
        yield text.count("\n", 0, match.start()) + 2, textwrap.dedent(match.group(2))


def _python_blocks():
    for md in _markdown_files():
        for first_line, source in _blocks_in(md.read_text(encoding="utf-8")):
            yield md.relative_to(_REPO), first_line, source


def _parse_blocks(text):
    for first_line, source in _blocks_in(text):
        try:
            yield first_line, ast.parse(source)
        except SyntaxError:
            # test_python_blocks_parse reports it; the AST checks can only run on blocks that parse.
            continue


def _parsed_blocks():
    for md in _markdown_files():
        for first_line, tree in _parse_blocks(md.read_text(encoding="utf-8")):
            yield md.relative_to(_REPO), first_line, tree


def _assignments(tree):
    # Keep every binding, not just the last: a block may rebind a name, and any binding can reach a call.
    assigned = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            assigned.setdefault(node.targets[0].id, []).append(node.value)
    return assigned


def _resolve(value, assigned):
    if isinstance(value, ast.Name) and value.id in assigned:
        return assigned[value.id]
    return [value]


def _call_name(call, assigned):
    func = call.func
    if isinstance(func, ast.Name):
        return None, func.id
    if isinstance(func, ast.Attribute):
        receivers = [r.attr for r in _resolve(func.value, assigned) if isinstance(r, ast.Attribute)]
        return (receivers[0] if receivers else None), func.attr
    return None, None


def _is_str(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _is_dict(node):
    return isinstance(node, ast.Dict) or (
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict"
    )


def _dict_items(node):
    if isinstance(node, ast.Dict):
        return [(k.value, v) for k, v in zip(node.keys, node.values) if _is_str(k)]
    if _is_dict(node):
        return [(kw.arg, kw.value) for kw in node.keywords if kw.arg]
    return []


def _has_dict(node):
    return isinstance(node, ast.List) and any(_is_dict(elt) for elt in node.elts)


def _keyword_values(call, assigned):
    """Yields (name, candidate value) for each keyword, expanding **{...} and **dict(...)."""
    for kw in call.keywords:
        if kw.arg is not None:
            for value in _resolve(kw.value, assigned):
                yield kw.arg, value
            continue
        for expanded in _resolve(kw.value, assigned):
            for name, item in _dict_items(expanded):
                for value in _resolve(item, assigned):
                    yield name, value


def _calls(tree):
    assigned = _assignments(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node, _call_name(node, assigned), assigned


def check_serving_query_messages(tree):
    return [
        (call.lineno, "serving_endpoints.query(messages=[{...}]) needs ChatMessage")
        for call, name, assigned in _calls(tree)
        if name == ("serving_endpoints", "query")
        for arg, value in _keyword_values(call, assigned)
        if arg == "messages" and _has_dict(value)
    ]


def _imports_sdk_chat_message(tree):
    return any(
        isinstance(node, ast.ImportFrom) and node.module == _SDK_SERVING_MODULE and any(a.name == "ChatMessage" for a in node.names)
        for node in ast.walk(tree)
    )


def check_chat_message_role(tree):
    # mlflow and LangChain ChatMessage classes take string roles; only the SDK dataclass needs ChatMessageRole.
    if not _imports_sdk_chat_message(tree):
        return []
    found = []
    for call, name, assigned in _calls(tree):
        if name[1] != "ChatMessage":
            continue
        roles = [value for arg, value in _keyword_values(call, assigned) if arg == "role"]
        if len(call.args) > _CHAT_MESSAGE_ROLE_POSITION:
            roles += _resolve(call.args[_CHAT_MESSAGE_ROLE_POSITION], assigned)
        found += [(call.lineno, f"ChatMessage(role={r.value!r}) needs ChatMessageRole") for r in roles if _is_str(r)]
    return found


def check_databricks_agents_imports(tree):
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("databricks.agents.tools"):
                found.append((node.lineno, f"from {node.module} import ..."))
            elif node.module == "databricks.agents" and any(a.name in ("ChatAgent", "tools") for a in node.names):
                found.append((node.lineno, "from databricks.agents import ChatAgent/tools"))
        elif isinstance(node, ast.Import):
            found += [(node.lineno, f"import {a.name}") for a in node.names if a.name.startswith("databricks.agents.tools")]
    return found


def _is_ai_search_create(call, name):
    return isinstance(call.func, ast.Attribute) and name[0] not in _SDK_SERVICES and name[1] in _AI_SEARCH_CREATE_METHODS


def _receiver_key(node):
    return ast.unparse(node) if isinstance(node, (ast.Name, ast.Attribute)) else None


def _is_index_create(node):
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("create_delta_sync_index", "create_index")
    )


def sync_before_ready_violations(trees):
    """Yields (block number, line, message) across one file's blocks, read in order.

    Creating a Delta Sync index starts its first sync, and a sync request while it is still provisioning is
    rejected. A create marks its variable pending (an unassigned create marks every receiver); wait_until_ready()
    on that variable, or its describe() in a loop condition (a hand-written readiness poll), clears it. A later
    block that rebinds the variable with get_index() starts a fresh standalone example, which also clears it.
    """
    pending = {}  # receiver -> block number of the create
    any_pending = None  # block number of an unassigned create
    cleared = set()  # receivers cleared since that unassigned create
    for block, tree in enumerate(trees):
        polled = {
            id(node)
            for loop in ast.walk(tree) if isinstance(loop, ast.While)
            for node in ast.walk(loop.test) if isinstance(node, ast.Call)
        }
        assigned_creates = set()
        events = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if _is_index_create(node.value):
                    assigned_creates.add(id(node.value))
                    events.append((node, "create", node.targets[0].id))
                elif isinstance(node.value, ast.Call) and _call_name(node.value, {})[1] == "get_index":
                    events.append((node, "rebind", node.targets[0].id))
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                attr, receiver = node.func.attr, node.func.value
                if attr == "wait_until_ready" and _is_index_create(receiver):
                    events.append((node, "chained_wait", None))
                elif attr == "wait_until_ready" or (attr == "describe" and id(node) in polled):
                    events.append((node, "wait", _receiver_key(receiver)))
                elif attr in ("sync", "sync_index"):
                    events.append((node, "chained" if _is_index_create(receiver) else "sync", _receiver_key(receiver)))
        for node in ast.walk(tree):
            if _is_index_create(node) and id(node) not in assigned_creates:
                events.append((node, "create", None))
        for node, kind, key in sorted(events, key=lambda e: (e[0].end_lineno, e[0].end_col_offset)):
            if kind == "create" and key is None:
                any_pending, cleared = block, set()
            elif kind == "chained_wait":
                any_pending = None
            elif kind == "create":
                pending[key] = block
            elif kind == "wait" or (kind == "rebind" and block != pending.get(key, block)):
                pending.pop(key, None)
                cleared.add(key)
            elif kind == "rebind" and any_pending is not None and block != any_pending:
                cleared.add(key)
            elif kind == "chained" or (kind == "sync" and (key in pending or (any_pending is not None and key not in cleared))):
                yield block, node.lineno, f"{node.func.attr}() before the new index is ready; wait_until_ready() first"


def check_sync_before_ready(tree):
    return [(lineno, message) for _, lineno, message in sync_before_ready_violations([tree])]


_AST_CHECKS = [
    check_serving_query_messages,
    check_chat_message_role,
    check_databricks_agents_imports,
    check_sync_before_ready,
]

_SELF_TEST_CASES = [
    (check_serving_query_messages, 'w.serving_endpoints.query(name="m", messages=[{"role": "user", "content": "q"}])', 1),
    (check_serving_query_messages, 'msgs = [{"role": "user"}]\nw.serving_endpoints.query(name="m", messages=msgs)', 1),
    (check_serving_query_messages, 'w.serving_endpoints.query(name="m", messages=[dict(role="user", content="q")])', 1),
    (check_serving_query_messages, 'w.serving_endpoints.query(name="m", messages=[ChatMessage(role=ChatMessageRole.USER, content="q")])', 0),
    (check_chat_message_role, 'from databricks.sdk.service.serving import ChatMessage\nChatMessage(role="user", content="q")', 1),
    (check_chat_message_role, 'from databricks.sdk.service.serving import ChatMessage\nr = "user"\nChatMessage(content="q", role=r)', 1),
    (check_chat_message_role, 'from databricks.sdk.service.serving import ChatMessage\nChatMessage("q", "user")', 1),
    (check_chat_message_role, 'from databricks.sdk.service.serving import ChatMessage\nChatMessage(role=ChatMessageRole.USER, content="q")', 0),
    (check_chat_message_role, 'from mlflow.types.llm import ChatMessage\nChatMessage(role="user", content="q")', 0),
    (check_chat_message_role, 'from langchain_core.messages import ChatMessage\nChatMessage(role="user", content="q")', 0),
    (check_databricks_agents_imports, "from databricks.agents import ChatAgent", 1),
    (check_databricks_agents_imports, "from databricks.agents.tools import VectorSearchRetrieverTool", 1),
    (check_databricks_agents_imports, "import databricks.agents.tools", 1),
    (check_databricks_agents_imports, "from databricks_langchain import VectorSearchRetrieverTool", 0),
    (check_sync_before_ready, 'i = client.create_delta_sync_index(endpoint_name="e", index_name="i", pipeline_type="TRIGGERED")\ni.sync()', 1),
    (check_sync_before_ready, 'client.create_delta_sync_index(index_name="i").sync()', 1),
    (check_sync_before_ready, 'client.create_delta_sync_index(index_name="i")\nindex = client.get_index(index_name="i")\nindex.sync()', 1),
    (check_sync_before_ready, 'w.vector_search_indexes.create_index(name="i")\nw.vector_search_indexes.sync_index(index_name="i")', 1),
    (check_sync_before_ready, 'i = client.create_delta_sync_index(index_name="i")\ni.wait_until_ready()\ni.sync()', 0),
    (check_sync_before_ready, 'index = client.get_index(index_name="i")\nindex.sync()', 0),
    (check_sync_before_ready, 'i = client.create_delta_sync_index(index_name="i")\nwhile not i.describe()["status"].get("ready"):\n    pass\ni.sync()', 0),
    (check_sync_before_ready, 'i = client.create_delta_sync_index_and_wait(index_name="i")\ni.sync()', 0),
    (check_sync_before_ready, 'i = client.create_delta_sync_index(index_name="i")\nj = client.get_index(index_name="j")\nj.wait_until_ready()\ni.sync()', 1),
    (check_sync_before_ready, 'i = client.create_delta_sync_index(index_name="i")\ni.describe()\ni.sync()', 1),
    (check_sync_before_ready, 'client.create_delta_sync_index(index_name="i").wait_until_ready()\nindex = client.get_index(index_name="i")\nindex.sync()', 0),
    (check_sync_before_ready, 'client.create_delta_sync_index(index_name="i").describe()\nindex = client.get_index(index_name="i")\nindex.sync()', 1),
]
_MULTI_BLOCK_SYNC_CASES = [
    # Create in one block, sync in a later one with no wait in between.
    ('```python\nindex = client.create_delta_sync_index(index_name="i")\n```\n\n```python\nindex.sync()\n```\n', 1),
    ('```python\nindex = client.create_delta_sync_index(index_name="i")\n```\n\n```python\nindex.wait_until_ready()\n```\n\n```python\nindex.sync()\n```\n', 0),
    # A later standalone example that rebinds the name with get_index().
    ('```python\nindex = client.create_delta_sync_index(index_name="i")\n```\n\n```python\nindex = client.get_index(index_name="i")\nindex.sync()\n```\n', 0),
]


class VectorSearchCodeBlocksTest(unittest.TestCase):
    def assertNoViolations(self, violations):
        if violations:
            self.fail(f"{len(violations)} violation(s):\n" + "\n".join(violations))

    def test_checks_fire_on_bad_snippets_only(self):
        for check, snippet, expected in _SELF_TEST_CASES:
            with self.subTest(check=check.__name__, snippet=snippet):
                self.assertEqual(len(check(ast.parse(snippet))), expected)
        for text, expected in _MULTI_BLOCK_SYNC_CASES:
            with self.subTest(check="sync_before_ready_violations", text=text):
                trees = [tree for _, tree in _parse_blocks(text)]
                self.assertEqual(len(list(sync_before_ready_violations(trees))), expected)
        self.assertTrue(_NONEXISTENT_HELPERS.search('manage_vs_index(action="sync")'))
        self.assertFalse(_NONEXISTENT_HELPERS.search("w.vector_search_indexes.sync_index(index_name=i)"))

    def test_every_check_has_a_firing_self_test(self):
        firing = {check for check, _, expected in _SELF_TEST_CASES if expected > 0}
        self.assertEqual([check.__name__ for check in _AST_CHECKS if check not in firing], [])

    def test_fence_shapes_and_line_offset(self):
        text = 'intro\n\n```py\nx = 1\n```\n\n1. Step:\n\n   ```python title="a.py"\n   y = (\n   ```\n'
        blocks = list(_blocks_in(text))
        self.assertEqual([source for _, source in blocks], ["x = 1\n", "y = (\n"])
        # Violations are reported at first_line + lineno - 1, so first_line must be the markdown line of the first code line.
        self.assertEqual([first_line for first_line, _ in blocks], [4, 10])
        self.assertEqual(text.splitlines()[blocks[1][0] - 1].strip(), "y = (")
        self.assertEqual(list(_blocks_in("```pyspark\nx\n```\n")), [])
        for fence in ("```Python", "```python3", "~~~py"):
            with self.subTest(fence=fence):
                close = fence[:3]
                self.assertEqual([source for _, source in _blocks_in(f"{fence}\nx = 1\n{close}\n")], ["x = 1\n"])
        # A ~~~ fence doesn't close on ```.
        self.assertEqual([source for _, source in _blocks_in("~~~py\nx = 1\n```\ny\n~~~\n")], ["x = 1\n```\ny\n"])

    def test_skill_has_ai_search_create_calls(self):
        count = sum(
            1
            for _, _, tree in _parsed_blocks()
            for call, name, _ in _calls(tree)
            if _is_ai_search_create(call, name)
        )
        self.assertGreaterEqual(count, _MIN_AI_SEARCH_CREATE_CALLS, f"AISearchClient create calls found under {_SKILL_DIR}")

    def test_python_blocks_parse(self):
        violations = []
        for path, first_line, source in _python_blocks():
            try:
                ast.parse(source)
            except SyntaxError as e:
                violations.append(f"{path}:{first_line + (e.lineno or 1) - 1}: {e.msg}")
        self.assertNoViolations(violations)

    def test_python_blocks_pass_ast_checks(self):
        violations = [
            f"{path}:{first_line + lineno - 1}: {message}"
            for path, first_line, tree in _parsed_blocks()
            for check in _AST_CHECKS
            if check is not check_sync_before_ready
            for lineno, message in check(tree)
        ]
        # The sync check reads each file's blocks in order: a walkthrough creates, waits and syncs in separate blocks.
        for md in _markdown_files():
            blocks = list(_parse_blocks(md.read_text(encoding="utf-8")))
            violations += [
                f"{md.relative_to(_REPO)}:{blocks[block][0] + lineno - 1}: {message}"
                for block, lineno, message in sync_before_ready_violations([tree for _, tree in blocks])
            ]
        self.assertNoViolations(violations)

    def test_no_nonexistent_helpers(self):
        violations = []
        for md in _markdown_files():
            for lineno, text in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
                for match in _NONEXISTENT_HELPERS.finditer(text):
                    violations.append(f"{md.relative_to(_REPO)}:{lineno}: {match.group(1)} does not exist")
        self.assertNoViolations(violations)


if __name__ == "__main__":
    unittest.main()
