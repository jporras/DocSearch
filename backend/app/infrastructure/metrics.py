from prometheus_client import Counter, Gauge, Histogram


HTTP_REQUESTS = Counter(
    "document_api_http_requests_total",
    "HTTP requests handled by the API",
    ["method", "path", "status"],
)
HTTP_DURATION = Histogram(
    "document_api_http_request_duration_seconds",
    "HTTP request duration",
    ["method", "path"],
)
SEARCH_DURATION = Histogram(
    "document_search_duration_seconds",
    "Full-text search duration",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.4, 0.75, 1.0, 2.5),
)
UPLOADS = Counter("document_uploads_total", "Documents accepted for processing")
QUEUE_DEPTH = Gauge("document_processing_stream_length", "Entries in the processing stream")
WORKER_PROCESSING_DURATION = Histogram(
    "document_worker_processing_duration_seconds",
    "Document processing duration in the worker",
)
WORKER_PROCESSED = Counter(
    "document_worker_processed_total",
    "Documents completed by the worker",
    ["outcome"],
)
WORKER_RETRIES = Counter("document_worker_retries_total", "Document processing retries")
WORKER_DLQ = Counter("document_worker_dead_letter_total", "Documents sent to the dead-letter stream")
WORKER_PENDING = Gauge("document_worker_pending_messages", "Pending messages in the worker group")
