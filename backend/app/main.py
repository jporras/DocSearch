from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response
from time import perf_counter
import redis

from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.infrastructure.config import settings
from app.infrastructure.database import close_pool, open_pool
from app.infrastructure.metrics import HTTP_DURATION, HTTP_REQUESTS, QUEUE_DEPTH


@asynccontextmanager
async def lifespan(_: FastAPI):
    open_pool()
    yield
    close_pool()


app = FastAPI(title="Buscador de Documentos Técnicos", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(documents_router)


@app.middleware("http")
async def record_http_metrics(request: Request, call_next):
    started = perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    HTTP_REQUESTS.labels(request.method, path, str(response.status_code)).inc()
    HTTP_DURATION.labels(request.method, path).observe(perf_counter() - started)
    return response


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        QUEUE_DEPTH.set(client.xlen(settings.queue_name))
    finally:
        client.close()
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"code": "VALIDATION_ERROR", "message": "Datos de entrada inválidos.", "details": exc.errors()},
    )


@app.exception_handler(Exception)
async def unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "message": "Ocurrió un error inesperado."},
    )
