"""singine Lambda stub — HTTP invocation + Kafka consumer.

Acts as a Lambda-like execution surface:
  POST /invoke            — synchronous invocation with JSON body
  GET  /health            — health check
  GET  /topics            — list consumed Kafka topics
  GET  /log               — last N invocations

Consumes from Kafka staging topics and applies publish transforms
(markdown, XML, JSON, mediawiki) before forwarding results.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("singine.lambda")

app = FastAPI(title="singine-lambda", version="0.1.0")

PORT = int(os.environ.get("SINGINE_LAMBDA_PORT", "8090"))
KAFKA_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9093")
TOPICS = [t.strip() for t in os.environ.get("SINGINE_LAMBDA_TOPICS", "singine.staging.geo").split(",")]
LOG_DIR = Path(os.environ.get("SINGINE_LOG_DIR", "/tmp/singine-gitlog"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

# In-memory ring buffer of recent invocations
_recent: Deque[Dict[str, Any]] = deque(maxlen=200)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record(event_type: str, payload: Dict[str, Any]) -> None:
    entry = {"at": _now(), "event": event_type, "payload": payload}
    _recent.appendleft(entry)
    # Write markdown fragment to log dir for git tracking
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    frag = LOG_DIR / f"{ts}-{event_type.lower().replace('.', '-')}.md"
    frag.write_text(
        f"## {event_type} {ts}\n\n```json\n{json.dumps(payload, indent=2)}\n```\n",
        encoding="utf-8",
    )


def _process_message(topic: str, key: str, value: Dict[str, Any]) -> Dict[str, Any]:
    """Apply publication transforms and return enriched payload."""
    from singine.zip_neighborhood_demo import render_markdown, render_mediawiki, render_xml

    # Wrap in minimal demo envelope to reuse renderers
    envelope = {
        "demo_id": key or "kafka-event",
        "title": f"Kafka event from {topic}",
        "generated_at": _now(),
        "topology": {
            "kafka": {"topic": topic, "consumer_group": "singine-lambda"},
            "rabbitmq": {
                "raw": {"exchange": "singine.raw.messaging", "routing_key": f"{key}.geo", "queue": f"{key}.raw.queue"},
                "staging": {"exchange": "singine.staging.messaging", "routing_key": f"{key}.staging", "queue": f"{key}.staging.queue"},
            },
            "lambda": {"function_name": "singine-lambda", "purpose": "streaming transforms"},
        },
        "datasets": [value] if isinstance(value, dict) else [],
        "messages": {"raw": [], "staging": [], "kafka": [{"topic": topic, "key": key, "payload": value}]},
    }
    return {
        "source_topic": topic,
        "key": key,
        "payload": value,
        "markdown": render_markdown(envelope),
        "xml": render_xml(envelope),
        "mediawiki": render_mediawiki(envelope),
    }


# ── Kafka consumer thread ─────────────────────────────────────────────────────

def _kafka_consumer_loop() -> None:
    try:
        from confluent_kafka import Consumer, KafkaError
    except ImportError:
        log.warning("confluent-kafka not installed; Kafka consumer disabled")
        return

    conf = {
        "bootstrap.servers": KAFKA_SERVERS,
        "group.id": "singine-lambda",
        "auto.offset.reset": "latest",
        "enable.auto.commit": True,
    }
    consumer = Consumer(conf)
    consumer.subscribe(TOPICS)
    log.info("Kafka consumer subscribed to: %s", TOPICS)

    while True:
        try:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    log.error("Kafka error: %s", msg.error())
                continue
            key = (msg.key() or b"").decode("utf-8", errors="replace")
            try:
                value = json.loads(msg.value().decode("utf-8"))
            except Exception:
                value = {"raw": msg.value().decode("utf-8", errors="replace")}
            result = _process_message(msg.topic(), key, value)
            _record("KAFKA_MESSAGE_PROCESSED", {"topic": msg.topic(), "key": key, "result_keys": list(result.keys())})
        except Exception as exc:
            log.error("Consumer error: %s", exc)
            time.sleep(2)


# ── HTTP endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "service": "singine-lambda", "at": _now()}


@app.get("/topics")
def topics() -> Dict[str, Any]:
    return {"topics": TOPICS, "kafka": KAFKA_SERVERS}


@app.get("/log")
def log_recent(n: int = 20) -> List[Dict[str, Any]]:
    return list(_recent)[:n]


@app.post("/invoke")
async def invoke(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    topic = body.get("topic", "singine.staging.geo")
    key = body.get("key", "notebook")
    payload = body.get("payload", body)
    result = _process_message(topic, key, payload)
    _record("HTTP_INVOKE", {"topic": topic, "key": key})
    return JSONResponse(content=result)


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    t = threading.Thread(target=_kafka_consumer_loop, daemon=True)
    t.start()
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
