class DocumentValidationError(ValueError):
    """The submitted document violates an ingestion rule."""


class ProcessingUnavailableError(RuntimeError):
    """The document could not be handed to asynchronous processing."""
