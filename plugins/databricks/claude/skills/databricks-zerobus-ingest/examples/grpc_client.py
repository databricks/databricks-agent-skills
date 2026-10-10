"""Minimal raw gRPC Zerobus producer: JSON records on EphemeralStream.

A model of what the SDKs do for you: the async ack loop (in-flight buffer,
offsets, purge on ack), backpressure, flush, close, and replay on a new stream.
Prefer an SDK in production.

Required environment variables:
- DATABRICKS_WORKSPACE_URL: workspace URL with https://
- DATABRICKS_WORKSPACE_ID: workspace ID
- DATABRICKS_CLIENT_ID: service principal client ID
- DATABRICKS_CLIENT_SECRET: service principal client secret
- ZEROBUS_TABLE_NAME: fully qualified table name (catalog.schema.table)
- ZEROBUS_SERVER_ENDPOINT: Zerobus endpoint, https://<workspace-id>.zerobus.<region>.cloud.databricks.com

Install: pip install grpcio grpcio-tools protobuf requests
Generate stubs: python -m grpc_tools.protoc -I<path-to-zerobus-sdk>/rust/sdk -I<path-to-zerobus-sdk>/purego/internal/zerobuspb/third_party \\
  --python_out=. --grpc_python_out=. <path-to-zerobus-sdk>/rust/sdk/zerobus_service.proto
"""
import json
import os
import queue
import threading
import time

import grpc
import requests

import zerobus_service_pb2 as zb

RPC_METHOD = "/databricks.zerobus.Zerobus/EphemeralStream"
NON_RETRYABLE = {
    grpc.StatusCode.INVALID_ARGUMENT,
    grpc.StatusCode.UNAUTHENTICATED,
    grpc.StatusCode.PERMISSION_DENIED,
    grpc.StatusCode.OUT_OF_RANGE,
    grpc.StatusCode.UNIMPLEMENTED,
    grpc.StatusCode.NOT_FOUND,
}

WORKSPACE_URL = os.environ.get("DATABRICKS_WORKSPACE_URL", "").rstrip("/")
WORKSPACE_ID = os.environ.get("DATABRICKS_WORKSPACE_ID", "")
CLIENT_ID = os.environ.get("DATABRICKS_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("DATABRICKS_CLIENT_SECRET", "")
TABLE_NAME = os.environ.get("ZEROBUS_TABLE_NAME", "")
# Host only, no scheme: <workspace-id>.zerobus.<region>.cloud.databricks.com
ENDPOINT_HOST = os.environ.get("ZEROBUS_SERVER_ENDPOINT", "").removeprefix("https://")


class ZerobusToken:
    """Table-scoped OAuth token (1-hour lifetime), refreshed 5 minutes early."""

    REFRESH_MARGIN_S = 300

    def __init__(self):
        self._token, self._expires_at = None, 0.0
        self._lock = threading.Lock()

    def get(self, force=False):
        with self._lock:
            if force or self._token is None or time.time() > self._expires_at - self.REFRESH_MARGIN_S:
                self._fetch()
            return self._token

    def _fetch(self):
        catalog, schema, _ = TABLE_NAME.split(".")
        authorization_details = [
            {"type": "unity_catalog_privileges", "privileges": ["USE CATALOG"],
             "object_type": "CATALOG", "object_full_path": catalog},
            {"type": "unity_catalog_privileges", "privileges": ["USE SCHEMA"],
             "object_type": "SCHEMA", "object_full_path": f"{catalog}.{schema}"},
            {"type": "unity_catalog_privileges", "privileges": ["SELECT", "MODIFY"],
             "object_type": "TABLE", "object_full_path": TABLE_NAME,
             "operations": ["zerobuswrite"]},
        ]
        resp = requests.post(
            f"{WORKSPACE_URL}/oidc/v1/token",
            auth=(CLIENT_ID, CLIENT_SECRET),
            data={
                "grant_type": "client_credentials",
                "scope": "all-apis",
                "resource": f"api://databricks/workspaces/{WORKSPACE_ID}/zerobusDirectWriteApi",
                "authorization_details": json.dumps(authorization_details),
            },
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        self._expires_at = time.time() + int(body.get("expires_in", 3600))


class RawZerobusStream:
    """One EphemeralStream. A sender generator and an ack-reader thread run the async ack loop."""

    def __init__(self, channel, token, table_name, max_inflight=10_000, on_ack=None):
        self._outbox = queue.Queue()
        self._inflight = {}                      # wire offset -> JSON payload (or list for a batch)
        self._lock = threading.Lock()
        self._acked_cv = threading.Condition(self._lock)
        self._space = threading.BoundedSemaphore(max_inflight)  # backpressure
        self._next_offset = 0                    # wire offsets start at 0 on every new stream
        self._acked = -1                         # highest durable wire offset
        self._on_ack = on_ack
        self.error = None                        # grpc.RpcError that ended the stream
        self.rotating = False                    # server sent close_stream_signal
        self.finished = threading.Event()        # stream is done accepting records: error, rotation, or close
        self._reader_done = False

        call = channel.stream_stream(
            RPC_METHOD,
            request_serializer=zb.EphemeralStreamRequest.SerializeToString,
            response_deserializer=zb.EphemeralStreamResponse.FromString,
        )
        metadata = (
            ("authorization", f"Bearer {token}"),
            ("x-databricks-zerobus-table-name", table_name),
        )
        self._responses = call(self._requests(table_name), metadata=metadata)
        first = next(self._responses)            # raises grpc.RpcError if creation fails
        if first.WhichOneof("payload") != "create_stream_response":
            raise RuntimeError(f"expected create_stream_response, got {first.WhichOneof('payload')}")
        self.stream_id = first.create_stream_response.stream_id
        threading.Thread(target=self._read_acks, daemon=True).start()

    def _requests(self, table_name):
        # First message: create the stream. Then stream ingest requests as they are queued.
        yield zb.EphemeralStreamRequest(
            create_stream=zb.CreateIngestStreamRequest(table_name=table_name, record_type=zb.JSON))
        while True:
            request = self._outbox.get()
            if request is None:                  # close(): half-close the request side
                return
            yield request

    def _admit(self):
        # Block only while the in-flight buffer is full (backpressure), never per record.
        while not self._space.acquire(timeout=1.0):
            if self.finished.is_set():
                raise RuntimeError("stream finished; reopen and replay unacked()")
        if self.finished.is_set():
            self._space.release()
            raise RuntimeError("stream finished; reopen and replay unacked()")

    def ingest(self, record):
        """Queue one record (dict or JSON string). Returns its wire offset without waiting for the ack."""
        payload = record if isinstance(record, str) else json.dumps(record)
        self._admit()
        with self._lock:                         # assign and enqueue under one lock to keep offsets in order
            offset = self._next_offset
            self._next_offset += 1
            self._inflight[offset] = payload
            self._outbox.put(zb.EphemeralStreamRequest(
                ingest_record=zb.IngestRecordRequest(offset_id=offset, json_record=payload)))
        return offset

    def ingest_batch(self, records):
        """Queue a list of records as one IngestRecordBatchRequest. One wire offset covers the batch."""
        payloads = [r if isinstance(r, str) else json.dumps(r) for r in records]
        self._admit()
        with self._lock:
            offset = self._next_offset
            self._next_offset += 1
            self._inflight[offset] = payloads
            self._outbox.put(zb.EphemeralStreamRequest(
                ingest_record_batch=zb.IngestRecordBatchRequest(
                    offset_id=offset, json_batch=zb.JsonRecordBatch(records=payloads))))
        return offset

    def _read_acks(self):
        try:
            for response in self._responses:
                kind = response.WhichOneof("payload")
                if kind == "ingest_record_response":
                    up_to = response.ingest_record_response.durability_ack_up_to_offset
                    with self._lock:
                        for offset in range(self._acked + 1, up_to + 1):   # cumulative ack
                            if self._inflight.pop(offset, None) is not None:
                                self._space.release()
                        self._acked = max(self._acked, up_to)
                        self._acked_cv.notify_all()
                    if self._on_ack:
                        self._on_ack(up_to)      # metrics or logging; keep it fast
                elif kind == "close_stream_signal":
                    # The server will close this stream after close_stream_signal.duration.
                    # Stop adding records here; acks for in-flight records keep arriving.
                    self.rotating = True
                    self.finished.set()
        except grpc.RpcError as err:
            self.error = err
        finally:
            self.finished.set()
            self._outbox.put(None)               # release the request generator
            with self._lock:
                self._reader_done = True
                self._acked_cv.notify_all()

    def flush(self, timeout=300.0):
        """Wait until everything queued so far is durable. Call at boundaries, not per record."""
        with self._lock:
            target = self._next_offset - 1
            self._acked_cv.wait_for(
                lambda: self._acked >= target or self._reader_done, timeout)
            if self._acked >= target:
                return
        raise RuntimeError(f"flush incomplete: acked {self._acked} of {target}; error={self.error}")

    def close(self, timeout=300.0):
        self.flush(timeout)
        self._outbox.put(None)

    def unacked(self):
        """Payloads not yet durable, in send order. Replay them on a new stream."""
        with self._lock:
            return [self._inflight[k] for k in sorted(self._inflight)]


def open_stream(channel, token, replay=(), on_ack=None):
    """Open a new stream and re-send unacked payloads first (they get new wire offsets)."""
    stream = RawZerobusStream(channel, token.get(), TABLE_NAME, on_ack=on_ack)
    for payload in replay:
        if isinstance(payload, list):
            stream.ingest_batch(payload)
        else:
            stream.ingest(payload)
    return stream


def reopen(old, channel, token, retries=4, backoff_s=2.0):
    """Recover like the SDKs: retry retryable errors with backoff, refresh the token on auth errors."""
    if old.error is not None and old.error.code() in NON_RETRYABLE \
            and old.error.code() != grpc.StatusCode.UNAUTHENTICATED:
        raise old.error
    if old.rotating:
        # Give in-flight records a chance to be acked, then half-close the old stream.
        try:
            old.flush(timeout=30.0)
        except RuntimeError:
            pass
        old._outbox.put(None)
    replay = old.unacked()                       # at-least-once: some of these may already be durable
    force_refresh = old.error is not None and old.error.code() == grpc.StatusCode.UNAUTHENTICATED
    for attempt in range(retries + 1):
        try:
            if force_refresh:
                token.get(force=True)
            return open_stream(channel, token, replay)
        except grpc.RpcError as err:
            if err.code() in NON_RETRYABLE and err.code() != grpc.StatusCode.UNAUTHENTICATED:
                raise
            force_refresh = err.code() == grpc.StatusCode.UNAUTHENTICATED
            if attempt == retries:
                raise
            time.sleep(backoff_s)


def main():
    token = ZerobusToken()
    channel = grpc.secure_channel(f"{ENDPOINT_HOST}:443", grpc.ssl_channel_credentials())
    stream = open_stream(channel, token, on_ack=lambda off: print(f"durable through wire offset {off}"))
    try:
        for i in range(1000):
            record = {"device_name": f"sensor-{i}", "temp": 20 + i % 5, "humidity": 55}
            while True:
                if stream.finished.is_set():     # failed or rotated by the server
                    stream = reopen(stream, channel, token)
                try:
                    stream.ingest(record)        # queues and returns; no per-record wait
                    break
                except RuntimeError:             # the stream finished mid-call; reopen and retry
                    continue
        while True:                              # flush at the boundary, then half-close
            try:
                stream.close()
                break
            except RuntimeError:
                if not stream.finished.is_set():
                    raise
                stream = reopen(stream, channel, token)
    finally:
        channel.close()


if __name__ == "__main__":
    main()
