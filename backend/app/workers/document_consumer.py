import logging
import os
import signal
import socket
from threading import Event
from time import perf_counter

import redis
from prometheus_client import start_http_server

from app.application.process_document import ProcessDocument
from app.infrastructure.config import settings
from app.infrastructure.extraction.document_extractor import DocumentExtractor
from app.infrastructure.messaging.redis_documents import RedisDocumentBus
from app.infrastructure.metrics import (
    WORKER_DLQ,
    WORKER_PENDING,
    WORKER_PROCESSED,
    WORKER_PROCESSING_DURATION,
    WORKER_RETRIES,
)
from app.infrastructure.persistence.postgres_documents import PostgresDocumentRepository


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
stopping = Event()


def build_process_document() -> ProcessDocument:
    return ProcessDocument(
        repository=PostgresDocumentRepository(),
        extractor=DocumentExtractor(),
        events=RedisDocumentBus(),
    )


def process(
    document_id: str,
    correlation_id: str | None = None,
    batch_id: str | None = None,
) -> bool:
    return build_process_document().execute(document_id, correlation_id, batch_id)


def update_pending_metric(client: redis.Redis) -> None:
    pending = client.xpending(settings.queue_name, settings.queue_group)
    WORKER_PENDING.set(int(pending.get("pending", 0)))


def run() -> None:
    start_http_server(settings.worker_metrics_port)
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    repository = PostgresDocumentRepository()
    events = RedisDocumentBus()
    consumer = f"{socket.gethostname()}-{os.getpid()}"
    try:
        client.xgroup_create(settings.queue_name, settings.queue_group, id="0", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise
    logger.info("Worker %s listening on stream %s", consumer, settings.queue_name)
    update_pending_metric(client)
    try:
        while not stopping.is_set():
            claimed = client.xautoclaim(
                settings.queue_name,
                settings.queue_group,
                consumer,
                min_idle_time=60_000,
                start_id="0-0",
                count=1,
            )
            claimed_messages = claimed[1] if len(claimed) > 1 else []
            batches = (
                [(settings.queue_name, claimed_messages)]
                if claimed_messages
                else client.xreadgroup(
                    settings.queue_group,
                    consumer,
                    {settings.queue_name: ">"},
                    count=1,
                    block=2000,
                )
            )
            for _, messages in batches:
                for message_id, fields in messages:
                    document_id = fields["document_id"]
                    correlation_id = fields.get("correlation_id")
                    batch_id = fields.get("batch_id")
                    attempt = int(fields.get("attempt", "1"))
                    acknowledge = False
                    started = perf_counter()
                    try:
                        process(document_id, correlation_id, batch_id)
                        WORKER_PROCESSED.labels("success").inc()
                        logger.info(
                            "Processed document_id=%s correlation_id=%s batch_id=%s attempt=%s",
                            document_id,
                            correlation_id,
                            batch_id,
                            attempt,
                        )
                        acknowledge = True
                    except Exception as exc:
                        logger.exception(
                            "Failed document_id=%s correlation_id=%s batch_id=%s attempt=%s",
                            document_id,
                            correlation_id,
                            batch_id,
                            attempt,
                        )
                        if attempt < settings.worker_max_attempts:
                            retry_fields = {**fields, "attempt": str(attempt + 1)}
                            client.xadd(
                                settings.queue_name,
                                retry_fields,
                            )
                            WORKER_RETRIES.inc()
                            acknowledge = True
                        else:
                            event = repository.mark_error(document_id, str(exc))
                            dead_letter_fields = {
                                **fields,
                                "attempt": str(attempt),
                                "error": str(exc)[:1000],
                            }
                            client.xadd(
                                settings.dead_letter_queue,
                                dead_letter_fields,
                            )
                            WORKER_DLQ.inc()
                            WORKER_PROCESSED.labels("error").inc()
                            acknowledge = True
                            if event:
                                events.publish(
                                    {
                                        **event,
                                        "correlation_id": correlation_id,
                                        "batch_id": batch_id,
                                    }
                                )
                    finally:
                        WORKER_PROCESSING_DURATION.observe(perf_counter() - started)
                        if acknowledge:
                            client.xack(settings.queue_name, settings.queue_group, message_id)
                            client.xdel(settings.queue_name, message_id)
                            update_pending_metric(client)
    finally:
        client.close()


def stop(*_: object) -> None:
    stopping.set()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    run()
