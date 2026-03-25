"""singine messaging pipeline — RabbitMQ raw/staging + Kafka streaming.

Provides a unified send() interface for notebook and CLI use. Gracefully
degrades when brokers are not reachable: messages are queued locally in
a SQLite buffer and the pipeline records a git log fragment regardless.

Architecture:

    Notebook / CLI
        │
        ▼
    pipeline.send(payload, stage="raw")
        │
        ├── RabbitMQ exchange: singine.raw.messaging
        │       routing_key: {domain}.geo.v1
        │       queue:       singine.raw.geo.queue
        │
        ▼  (Lambda or consumer promotes to staging)
    pipeline.send(payload, stage="staging")
        │
        ├── RabbitMQ exchange: singine.staging.messaging
        │       routing_key: {domain}.geo.v1
        │       queue:       singine.staging.geo.queue
        │
        ▼  (Lambda publishes to Kafka)
    Kafka topic: singine.datastreaming.zip.v1
        │        singine.datastreaming.lifecycle.v1
        │        singine.datastreaming.language.v1
        │
        ▼
    Lambda stub: http://localhost:8090/invoke
        │
        ▼
    Transforms → markdown / xml / json / mediawiki

Usage (notebook):
    from singine.pipeline import Pipeline
    p = Pipeline()
    p.send({"zip_code": "10001", ...}, stage="raw")
    p.send({"zip_code": "10001", ...}, stage="staging")
    p.stream({"zip_code": "10001", ...}, topic="singine.datastreaming.zip.v1")
    p.invoke({"zip_code": "10001", ...})   # → Lambda HTTP

    # Or use the module-level shorthand
    import singine.pipeline as pipeline
    pipeline.send(payload)
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .gitlog import GitLog


# ── Configuration ─────────────────────────────────────────────────────────────

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://singine:singine@localhost:5672/")
KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9093")
LAMBDA_URL = os.environ.get("SINGINE_LAMBDA_URL", "http://localhost:8090/invoke")

EXCHANGE_RAW = "singine.raw.messaging"
EXCHANGE_STAGING = "singine.staging.messaging"

KAFKA_TOPICS = {
    "zip": "singine.datastreaming.zip.v1",
    "lifecycle": "singine.datastreaming.lifecycle.v1",
    "language": "singine.datastreaming.language.v1",
    "activity": "singine.events.activity",
}

LOCAL_BUFFER_DB = Path.home() / ".singine" / "pipeline-buffer.db"


# ── Local buffer (SQLite) ─────────────────────────────────────────────────────

def _buffer_ddl() -> str:
    return """
CREATE TABLE IF NOT EXISTS pipeline_message (
    message_id  TEXT PRIMARY KEY,
    stage       TEXT NOT NULL,
    exchange    TEXT,
    routing_key TEXT,
    topic       TEXT,
    payload     TEXT NOT NULL,
    sent_at     TEXT NOT NULL,
    delivered   INTEGER NOT NULL DEFAULT 0,
    error       TEXT
);
"""


def _buffer_write(
    db: Path,
    stage: str,
    exchange: Optional[str],
    routing_key: Optional[str],
    topic: Optional[str],
    payload: Dict[str, Any],
    delivered: bool = False,
    error: Optional[str] = None,
) -> str:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.executescript(_buffer_ddl())
    mid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO pipeline_message VALUES (?,?,?,?,?,?,?,?,?)",
        (mid, stage, exchange, routing_key, topic,
         json.dumps(payload, ensure_ascii=False),
         datetime.now(timezone.utc).isoformat(),
         1 if delivered else 0, error),
    )
    conn.commit()
    conn.close()
    return mid


# ── Broker adapters ───────────────────────────────────────────────────────────

class _RabbitMQAdapter:
    def __init__(self, url: str) -> None:
        self.url = url
        self._available: Optional[bool] = None

    def _check(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import pika  # noqa: F401
            params = pika.URLParameters(self.url)
            params.socket_timeout = 2
            conn = pika.BlockingConnection(params)
            conn.close()
            self._available = True
        except Exception:
            self._available = False
        return self._available

    def publish(
        self,
        exchange: str,
        routing_key: str,
        payload: Dict[str, Any],
    ) -> bool:
        if not self._check():
            return False
        try:
            import pika

            params = pika.URLParameters(self.url)
            params.socket_timeout = 3
            conn = pika.BlockingConnection(params)
            ch = conn.channel()
            ch.exchange_declare(exchange=exchange, exchange_type="topic", durable=True)
            ch.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=json.dumps(payload, ensure_ascii=False).encode(),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # persistent
                    content_type="application/json",
                ),
            )
            conn.close()
            return True
        except Exception:
            return False


class _KafkaAdapter:
    def __init__(self, bootstrap: str) -> None:
        self.bootstrap = bootstrap
        self._available: Optional[bool] = None

    def _check(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            from confluent_kafka import Producer

            p = Producer({"bootstrap.servers": self.bootstrap, "socket.timeout.ms": 2000})
            p.flush(timeout=2)
            self._available = True
        except Exception:
            self._available = False
        return self._available

    def produce(self, topic: str, key: str, payload: Dict[str, Any]) -> bool:
        if not self._check():
            return False
        try:
            from confluent_kafka import Producer

            p = Producer({"bootstrap.servers": self.bootstrap})
            p.produce(
                topic,
                key=key.encode(),
                value=json.dumps(payload, ensure_ascii=False).encode(),
            )
            p.flush(timeout=5)
            return True
        except Exception:
            return False


class _LambdaAdapter:
    def __init__(self, url: str) -> None:
        self.url = url

    def invoke(self, topic: str, key: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            import urllib.error
            import urllib.request

            body = json.dumps({"topic": topic, "key": key, "payload": payload}).encode()
            req = urllib.request.Request(
                self.url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read())
        except Exception:
            return None


# ── Pipeline ──────────────────────────────────────────────────────────────────

class Pipeline:
    """Unified send interface for RabbitMQ + Kafka + Lambda."""

    def __init__(
        self,
        *,
        rabbitmq_url: str = RABBITMQ_URL,
        kafka_bootstrap: str = KAFKA_BOOTSTRAP,
        lambda_url: str = LAMBDA_URL,
        buffer_db: Path = LOCAL_BUFFER_DB,
        gitlog: Optional[GitLog] = None,
        actor: str = "singine",
    ) -> None:
        self._rabbit = _RabbitMQAdapter(rabbitmq_url)
        self._kafka = _KafkaAdapter(kafka_bootstrap)
        self._lambda = _LambdaAdapter(lambda_url)
        self._buffer = buffer_db
        self._log = gitlog or GitLog(actor=actor)
        self.actor = actor

    # ── RabbitMQ ──────────────────────────────────────────────────────────────

    def send(
        self,
        payload: Dict[str, Any],
        *,
        stage: str = "raw",
        domain: str = "geo",
        version: str = "v1",
    ) -> Dict[str, Any]:
        """Send to RabbitMQ raw or staging exchange."""
        exchange = EXCHANGE_RAW if stage == "raw" else EXCHANGE_STAGING
        routing_key = f"{self.actor}.{domain}.{version}"
        delivered = self._rabbit.publish(exchange, routing_key, payload)
        mid = _buffer_write(
            self._buffer, stage, exchange, routing_key, None, payload, delivered
        )
        self._log.record(
            f"PIPELINE_{stage.upper()}_SEND",
            {"message_id": mid, "exchange": exchange, "routing_key": routing_key,
             "delivered": delivered, "payload_keys": list(payload.keys())},
            note=f"RabbitMQ {stage}: {routing_key}",
        )
        return {
            "message_id": mid,
            "stage": stage,
            "exchange": exchange,
            "routing_key": routing_key,
            "delivered": delivered,
            "buffered_locally": not delivered,
        }

    # ── Kafka ─────────────────────────────────────────────────────────────────

    def stream(
        self,
        payload: Dict[str, Any],
        *,
        topic: Optional[str] = None,
        key: Optional[str] = None,
        domain: str = "zip",
    ) -> Dict[str, Any]:
        """Produce to a Kafka streaming topic."""
        resolved_topic = topic or KAFKA_TOPICS.get(domain, KAFKA_TOPICS["zip"])
        msg_key = key or payload.get("zip_code", str(uuid.uuid4())[:8])
        delivered = self._kafka.produce(resolved_topic, msg_key, payload)
        mid = _buffer_write(
            self._buffer, "stream", None, None, resolved_topic, payload, delivered
        )
        self._log.record(
            "PIPELINE_STREAM",
            {"message_id": mid, "topic": resolved_topic, "key": msg_key, "delivered": delivered},
            note=f"Kafka stream: {resolved_topic}",
        )
        return {
            "message_id": mid,
            "topic": resolved_topic,
            "key": msg_key,
            "delivered": delivered,
            "buffered_locally": not delivered,
        }

    # ── Lambda ────────────────────────────────────────────────────────────────

    def invoke(
        self,
        payload: Dict[str, Any],
        *,
        topic: Optional[str] = None,
        key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Invoke Lambda stub and return publication transforms."""
        resolved_topic = topic or KAFKA_TOPICS["zip"]
        msg_key = key or payload.get("zip_code", "notebook")
        result = self._lambda.invoke(resolved_topic, msg_key, payload)
        self._log.record(
            "PIPELINE_LAMBDA_INVOKE",
            {"topic": resolved_topic, "key": msg_key, "invoked": result is not None},
            note=f"Lambda invoke: {resolved_topic}",
        )
        return result or {
            "invoked": False,
            "note": "Lambda stub not reachable; run: docker compose -f docker/docker-compose.messaging.yml up -d",
            "payload": payload,
        }

    # ── Full pipeline (raw → staging → stream → invoke) ───────────────────────

    def publish(
        self,
        payload: Dict[str, Any],
        *,
        domain: str = "geo",
        key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Full pipeline: raw RabbitMQ → staging RabbitMQ → Kafka stream → Lambda."""
        raw = self.send(payload, stage="raw", domain=domain)
        staging = self.send(payload, stage="staging", domain=domain)
        stream = self.stream(payload, domain=domain, key=key)
        result = self.invoke(payload, topic=stream["topic"], key=stream["key"])
        return {
            "raw": raw,
            "staging": staging,
            "stream": stream,
            "lambda": result,
        }

    def buffer_summary(self) -> List[Dict[str, Any]]:
        """Return summary of locally buffered messages."""
        if not self._buffer.exists():
            return []
        conn = sqlite3.connect(str(self._buffer))
        conn.executescript(_buffer_ddl())
        rows = conn.execute(
            "SELECT message_id, stage, exchange, topic, delivered, sent_at FROM pipeline_message ORDER BY sent_at DESC LIMIT 50"
        ).fetchall()
        conn.close()
        return [
            {"message_id": r[0], "stage": r[1], "exchange": r[2], "topic": r[3],
             "delivered": bool(r[4]), "sent_at": r[5]}
            for r in rows
        ]


# ── Module-level default instance ────────────────────────────────────────────

_default: Optional[Pipeline] = None


def _get() -> Pipeline:
    global _default
    if _default is None:
        _default = Pipeline()
    return _default


def send(payload: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
    return _get().send(payload, **kwargs)


def stream(payload: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
    return _get().stream(payload, **kwargs)


def invoke(payload: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
    return _get().invoke(payload, **kwargs)


def publish(payload: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
    return _get().publish(payload, **kwargs)
