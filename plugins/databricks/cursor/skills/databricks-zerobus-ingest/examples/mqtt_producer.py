"""Non-blocking MQTT v5 producer for Zerobus Ingest.

Publishes JSON records with QoS 1 acknowledgments to a Zerobus table.
Uses paho-mqtt callbacks for async publishing and automatic reconnection
with token refresh. Demonstrates the non-blocking pattern: publish records
as fast as the buffer fills, call flush() at boundaries, and handle acks
in a callback.

Required environment variables:
- DATABRICKS_WORKSPACE_URL: workspace URL with https://
- DATABRICKS_WORKSPACE_ID: workspace ID
- DATABRICKS_CLIENT_ID: service principal client ID
- DATABRICKS_CLIENT_SECRET: service principal client secret
- ZEROBUS_TABLE_NAME: fully qualified table name (catalog.schema.table)
- ZEROBUS_SERVER_ENDPOINT: Zerobus endpoint; the MQTT host is the same host without https://

Install: pip install "paho-mqtt>=2,<3" requests
"""
import collections
import json
import os
import ssl
import threading
import time
import uuid

import paho.mqtt.client as mqtt
import requests

MAX_PACKET_BYTES = 64 * 1024   # Zerobus limit for a complete MQTT packet after CONNECT
RECEIVE_MAXIMUM = 4096         # Zerobus CONNACK Receive Maximum: QoS 1 messages in flight per connection


def fetch_zerobus_token():
    """Table-scoped OAuth token for the service principal (same request as the docs)."""
    workspace_url = os.environ["DATABRICKS_WORKSPACE_URL"].rstrip("/")
    workspace_id = os.environ["DATABRICKS_WORKSPACE_ID"]
    table_name = os.environ["ZEROBUS_TABLE_NAME"]
    catalog, schema, _ = table_name.split(".")
    authorization_details = [
        {"type": "unity_catalog_privileges", "privileges": ["USE CATALOG"],
         "object_type": "CATALOG", "object_full_path": catalog},
        {"type": "unity_catalog_privileges", "privileges": ["USE SCHEMA"],
         "object_type": "SCHEMA", "object_full_path": f"{catalog}.{schema}"},
        {"type": "unity_catalog_privileges", "privileges": ["SELECT", "MODIFY"],
         "object_type": "TABLE", "object_full_path": table_name},
    ]
    response = requests.post(
        f"{workspace_url}/oidc/v1/token",
        auth=(os.environ["DATABRICKS_CLIENT_ID"], os.environ["DATABRICKS_CLIENT_SECRET"]),
        data={
            "grant_type": "client_credentials",
            "scope": "all-apis",
            "resource": f"api://databricks/workspaces/{workspace_id}/zerobusDirectWriteApi",
            "authorization_details": json.dumps(authorization_details),
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


class ZerobusMqttPublisher:
    """Non-blocking QoS 1 publisher for one Zerobus table. Call publish() from one thread."""

    def __init__(self, host, table_name, token_fn, max_inflight=1000, on_ack=None, on_error=None,
                 connect_timeout=30, max_connect_attempts=5):
        if not 1 <= max_inflight <= RECEIVE_MAXIMUM:
            raise ValueError(f"max_inflight must be between 1 and {RECEIVE_MAXIMUM}")
        self._host, self._table, self._token_fn = host, table_name, token_fn
        self._max_inflight = max_inflight
        self._on_ack = on_ack or (lambda record: None)
        self._on_error = on_error or (lambda record, reason: print(f"not acknowledged ({reason}): {record}"))
        self._connect_timeout = connect_timeout
        self._max_connect_attempts = max_connect_attempts
        # The 64 KiB limit covers the whole PUBLISH packet: fixed header (up to 5 bytes),
        # topic (2 + length), packet ID (2), and properties length (1).
        self._max_payload = MAX_PACKET_BYTES - 5 - (2 + len(table_name.encode("utf-8"))) - 2 - 1

        self._slots = threading.BoundedSemaphore(max_inflight)  # backpressure
        self._lock = threading.Lock()         # never held while calling into the live paho client
        self._idle = threading.Condition(self._lock)
        self._inflight = {}                   # mid -> (record, payload) on the current connection
        self._early = {}                      # mid -> reason code, when PUBACK beats publish() returning
        self._retry = collections.deque()     # unacknowledged records to resend after a reconnect
        self._client = None
        self._connected = threading.Event()
        self._connack = threading.Event()
        self._connack_reason = None
        self._ensure_connected()

    # ---- public API ----
    def publish(self, record):
        """Queue one JSON record and return. Blocks only while max_inflight records await PUBACK."""
        payload = json.dumps(record, separators=(",", ":")).encode("utf-8")
        if len(payload) > self._max_payload:
            # An oversized packet closes the connection and is always rejected: never retry it.
            raise ValueError(f"record is {len(payload)} bytes; the limit is {self._max_payload}")
        self._slots.acquire()
        try:
            self._publish_on(self._ensure_connected(), record, payload)
        except BaseException:
            self._slots.release()
            raise

    def flush(self, timeout=None):
        """Durability boundary: return once every published record has a PUBACK."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            client = self._ensure_connected()  # after a disconnect: reconnect and resend
            self._drain(client)
            with self._lock:
                if not self._inflight and not self._retry:
                    return
                self._idle.wait(0.5)
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError("records still waiting for PUBACK")

    def close(self, timeout=None):
        try:
            self.flush(timeout)
        finally:
            if self._client is not None:
                self._client.disconnect()
                self._client.loop_stop()

    # ---- internals ----
    def _publish_on(self, client, record, payload):
        info = client.publish(self._table, payload, qos=1)   # topic = the full table name
        with self._lock:
            if info.rc != mqtt.MQTT_ERR_SUCCESS or client is not self._client:
                self._retry.append((record, payload))           # resend once reconnected
                return
            early = self._early.pop(info.mid, None)
            if early is None:
                self._inflight[info.mid] = (record, payload)
        if early is not None:
            self._finish(record, early)

    def _drain(self, client):
        while True:                           # resend unacknowledged records, oldest first
            with self._lock:
                if not self._retry or client is not self._client or not self._connected.is_set():
                    return
                record, payload = self._retry.popleft()
            self._publish_on(client, record, payload)

    def _finish(self, record, reason_code):
        self._slots.release()
        if reason_code.value == 0:            # treat any other PUBACK reason code as not acknowledged
            self._on_ack(record)
        else:
            self._on_error(record, reason_code)

    def _ensure_connected(self):
        delay = 1
        for attempt in range(1, self._max_connect_attempts + 1):
            if self._connected.is_set():
                return self._client
            try:
                self._reconnect()
                return self._client
            except (OSError, RuntimeError, TimeoutError) as err:
                if attempt == self._max_connect_attempts:
                    raise
                print(f"connect attempt {attempt} failed: {err}; retrying in {delay}s")
                time.sleep(delay)
                delay = min(delay * 2, 30)
        return self._client

    def _reconnect(self):
        client, connect_props = self._new_client()   # fresh token: credentials are checked only at CONNECT
        with self._lock:
            old, self._client = self._client, client
            # No PUBACK means unacknowledged. The record may already be durable, so resending it
            # can create a duplicate (usually fine; see Delivery in the concepts table).
            self._retry.extend(self._inflight.values())
            self._inflight.clear()
            self._early.clear()
            self._connack.clear()
            self._connack_reason = None
        if old is not None:
            old.disconnect()
            old.loop_stop()
        result = client.connect(self._host, port=8883, keepalive=60, clean_start=True,
                                properties=connect_props)
        if result != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT connect failed: {mqtt.error_string(result)}")
        client.loop_start()
        if not self._connack.wait(self._connect_timeout) or not self._connected.is_set():
            client.disconnect()
            client.loop_stop()
            raise RuntimeError(f"CONNECT not accepted: {self._connack_reason or 'no CONNACK'}")
        self._drain(client)

    def _new_client(self):
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"zerobus-mqtt-{uuid.uuid4()}",  # unique per connection, at most 128 bytes
            protocol=mqtt.MQTTv5,
            reconnect_on_failure=False,                # reconnect here, with a fresh token
        )
        client.max_inflight_messages_set(self._max_inflight)  # paho's default is 20
        client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)
        client.on_connect = self._on_connect
        client.on_publish = self._on_publish
        client.on_disconnect = self._on_disconnect
        props = mqtt.Properties(mqtt.PacketTypes.CONNECT)
        props.UserProperty = [
            ("Authorization", f"Bearer {self._token_fn()}"),
            ("x-databricks-zerobus-table-name", self._table),
        ]
        return client, props

    # ---- paho callbacks: they run on the network thread, so keep them fast ----
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if client is not self._client:
            return
        self._connack_reason = reason_code
        if not reason_code.is_failure:
            server_max = getattr(properties, "ReceiveMaximum", None)
            if server_max is not None and server_max < self._max_inflight:
                print(f"warning: server Receive Maximum {server_max} is below max_inflight {self._max_inflight}")
            self._connected.set()
        self._connack.set()

    def _on_publish(self, client, userdata, mid, reason_code, properties):
        with self._lock:
            if client is not self._client:
                return                        # late PUBACK from a replaced connection
            entry = self._inflight.pop(mid, None)
            if entry is None:
                self._early[mid] = reason_code
                return
            if not self._inflight:
                self._idle.notify_all()
        self._finish(entry[0], reason_code)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        if client is not self._client:
            return
        if self._connack_reason is None:
            self._connack_reason = reason_code
        self._connected.clear()
        self._connack.set()
        with self._lock:
            self._idle.notify_all()


def main():
    """Usage example: publish records and track acknowledgments."""
    acked = 0

    def on_ack(record):               # runs on paho's network thread; keep it fast
        nonlocal acked
        acked += 1

    def on_error(record, reason):     # not acknowledged: apply your retry or dead-letter policy
        print(f"not acknowledged ({reason}): {record['event_id']}")

    publisher = ZerobusMqttPublisher(
        os.environ["ZEROBUS_SERVER_ENDPOINT"].removeprefix("https://"), os.environ["ZEROBUS_TABLE_NAME"], fetch_zerobus_token,
        max_inflight=1000, on_ack=on_ack, on_error=on_error,
    )
    try:
        for i in range(10_000):
            publisher.publish({"event_id": str(uuid.uuid4()), "device_name": f"sensor-{i % 10}",
                               "temp": 20 + i % 15, "humidity": 55})   # queues and returns
        publisher.flush()             # durability boundary: every record has a PUBACK
        print(f"{acked} records durable")
    finally:
        publisher.close()


if __name__ == "__main__":
    main()
