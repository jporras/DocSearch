import json
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any

import redis
import redis.asyncio as async_redis

from app.infrastructure.config import settings
from app.infrastructure.metrics import QUEUE_DEPTH


def channel_for(document_id: str) -> str:
    return f"documents:events:{document_id}"


class RedisDocumentBus:
    def enqueue(
        self,
        document_id: str,
        correlation_id: str,
        batch_id: str | None = None,
    ) -> None:
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            fields = {
                "event_type": "document.process",
                "schema_version": "1",
                "document_id": document_id,
                "correlation_id": correlation_id,
                "attempt": "1",
                "created_at": datetime.now(UTC).isoformat(),
            }
            if batch_id:
                fields["batch_id"] = batch_id
            client.xadd(settings.queue_name, fields)
            QUEUE_DEPTH.set(client.xlen(settings.queue_name))
        finally:
            client.close()

    def publish(self, payload: dict[str, Any]) -> None:
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            client.publish(channel_for(str(payload["id"])), json.dumps(payload, default=str))
        finally:
            client.close()

    async def stream(
        self,
        document_id: str,
        get_current: Callable[[], dict[str, Any] | None],
    ) -> AsyncIterator[str]:
        client = async_redis.Redis.from_url(settings.redis_url, decode_responses=True)
        pubsub = client.pubsub()
        await pubsub.subscribe(channel_for(document_id))
        try:
            current = get_current()
            if current:
                yield f"event: snapshot\ndata: {json.dumps(current, default=str)}\n\n"
                if current["status"] in {"INDEXED", "ERROR"}:
                    return
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
                if message and message.get("type") == "message":
                    yield f"event: document_status\ndata: {message['data']}\n\n"
                else:
                    yield ": keepalive\n\n"
        finally:
            await pubsub.unsubscribe(channel_for(document_id))
            await pubsub.aclose()
            await client.aclose()
