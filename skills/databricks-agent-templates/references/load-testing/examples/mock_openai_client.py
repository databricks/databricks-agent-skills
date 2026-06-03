"""
Mock AsyncOpenAI client that simulates LLM streaming responses.

Handles two types of calls in the agent flow:
  Call 1 (tool call): When messages don't contain tool results, returns a
    streamed tool call for get_current_time().
  Call 2 (summarize): When messages contain tool results, returns a streamed
    text response summarizing the time.

Uses MOCK_CHUNK_DELAY_MS and MOCK_CHUNK_COUNT env vars to control timing.
"""

import asyncio
import os
import time
import uuid


# Response text for the summary (call 2) — split into chunks during streaming
SUMMARY_TEXT = (
    "The current time is 2026-04-01T00:00:00+00:00. "
    "That's April 1st, 2026 at midnight UTC. "
    "Time zones are regions of the Earth that observe a uniform standard time. "
    "They are based on longitudinal divisions of the globe, generally 15 degrees wide, "
    "corresponding to one-hour intervals from Coordinated Universal Time (UTC). "
    "The concept of standard time zones was first proposed in the late 19th century "
    "to replace the many local solar times that were previously used. "
    "Before time zones, each city set its clocks according to the local position of the sun, "
    "which made scheduling train services and telegraph communications very difficult. "
    "The adoption of time zones greatly simplified commerce and travel across long distances. "
    "Today there are 24 primary time zones, though some regions use offsets of 30 or 45 minutes. "
    "Countries like India use a single time zone for the entire nation despite spanning a wide longitude, "
    "while countries like Russia and the United States use multiple time zones. "
    "Daylight saving time further complicates the picture, as many regions shift their clocks forward "
    "by one hour during summer months to extend evening daylight. "
    "Modern computing systems typically store times in UTC and convert to local time zones for display, "
    "which avoids many of the ambiguities that arise from daylight saving transitions "
    "and varying regional offset rules."
)


def _get_config():
    chunk_count = int(os.environ.get("MOCK_CHUNK_COUNT", "80"))
    chunk_delay_s = int(os.environ.get("MOCK_CHUNK_DELAY_MS", "10")) / 1000
    return chunk_count, chunk_delay_s


def _has_tool_output(messages):
    """Check if any message contains tool/function output (indicating call 2)."""
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role", "")
            if role == "tool":
                return True
        elif hasattr(msg, "role") and msg.role == "tool":
            return True
    return False


def _make_chunk(chunk_id, content=None, tool_calls=None, finish_reason=None, usage=None):
    """Build a ChatCompletionChunk-like object using SimpleNamespace for attribute access."""
    from types import SimpleNamespace

    delta = SimpleNamespace(
        content=content,
        role="assistant" if (content is not None or tool_calls is not None) else None,
        tool_calls=tool_calls,
        refusal=None,
        function_call=None,
    )

    choice = SimpleNamespace(
        delta=delta,
        finish_reason=finish_reason,
        index=0,
        logprobs=None,
    )

    chunk = SimpleNamespace(
        id=chunk_id,
        choices=[choice],
        created=int(time.time()),
        model="mock-model",
        object="chat.completion.chunk",
        service_tier=None,
        system_fingerprint=None,
        usage=usage,
    )
    return chunk


def _make_tool_call_delta(index=0, tc_id=None, name=None, arguments=None):
    """Build a tool call delta object."""
    from types import SimpleNamespace

    func = None
    if name is not None or arguments is not None:
        func = SimpleNamespace(
            name=name,
            arguments=arguments,
        )

    return SimpleNamespace(
        index=index,
        id=tc_id,
        function=func,
        type="function" if tc_id else None,
    )


class MockAsyncStream:
    """Async iterator that yields ChatCompletionChunk objects."""

    def __init__(self, chunks):
        self._chunks = chunks
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def close(self):
        pass


class _MockCompletions:
    """Mock chat.completions with a create() method."""

    async def create(self, **kwargs):
        messages = kwargs.get("messages", [])
        is_stream = kwargs.get("stream", False)

        if _has_tool_output(messages):
            # Call 2: summarize — return text response
            return await self._stream_text_response()
        else:
            # Call 1: decide to call tool — return tool call
            return await self._stream_tool_call()

    async def _stream_tool_call(self):
        """Simulate LLM deciding to call get_current_time()."""
        chunk_count, chunk_delay_s = _get_config()
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        call_id = f"call_{uuid.uuid4().hex[:24]}"

        chunks = []

        # First chunk: role + tool call name
        chunks.append(_make_chunk(
            chunk_id,
            tool_calls=[_make_tool_call_delta(
                index=0,
                tc_id=call_id,
                name="get_current_time",
                arguments="",
            )],
        ))

        # Stream the arguments "{}" across a few chunks to simulate real behavior
        for arg_part in ["{", "}"]:
            chunks.append(_make_chunk(
                chunk_id,
                tool_calls=[_make_tool_call_delta(
                    index=0,
                    arguments=arg_part,
                )],
            ))

        # Final chunk: finish_reason = tool_calls
        chunks.append(_make_chunk(chunk_id, finish_reason="tool_calls"))

        # Tool call chunks stream instantly (no delay)
        return MockAsyncStream(chunks)

    async def _stream_text_response(self):
        """Simulate LLM summarizing the tool output."""
        chunk_count, chunk_delay_s = _get_config()
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

        # Split summary text into chunks
        words = SUMMARY_TEXT.split()
        text_chunks = []
        base_size = max(1, len(words) // chunk_count)
        remainder = len(words) % chunk_count
        idx = 0
        for i in range(chunk_count):
            size = base_size + (1 if i < remainder else 0)
            if idx < len(words):
                text_chunks.append(" ".join(words[idx:idx + size]) + " ")
                idx += size

        chunks = []

        # First chunk: role
        chunks.append(_make_chunk(chunk_id, content=""))

        # Text delta chunks with delays
        for text in text_chunks:
            chunks.append(_make_chunk(chunk_id, content=text))

        # Final chunk: finish_reason = stop
        chunks.append(_make_chunk(chunk_id, finish_reason="stop"))

        return _MockDelayedStream(chunks, chunk_delay_s)


class _MockDelayedStream:
    """Async iterator that adds delays between chunks to simulate LLM token generation."""

    def __init__(self, chunks, delay_s):
        self._chunks = chunks
        self._delay_s = delay_s
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        # Add delay between content chunks (skip first role chunk and last finish chunk)
        if self._delay_s > 0 and 1 < self._index < len(self._chunks):
            await asyncio.sleep(self._delay_s)
        return chunk

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def close(self):
        pass


class _MockChat:
    """Mock client.chat namespace."""

    def __init__(self):
        self.completions = _MockCompletions()


class MockAsyncOpenAI:
    """
    Drop-in replacement for AsyncDatabricksOpenAI that returns mock streaming responses.

    Simulates:
      - Call 1: LLM decides to invoke get_current_time (tool call response)
      - Call 2: LLM summarizes tool output (text streaming response)

    Timing controlled by MOCK_CHUNK_DELAY_MS and MOCK_CHUNK_COUNT env vars.
    """

    def __init__(self, **kwargs):
        self.chat = _MockChat()
        # Satisfy any attribute checks the SDK might do
        self.api_key = "mock-key"
        self.base_url = "http://mock"
