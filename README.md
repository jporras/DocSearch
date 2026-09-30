# Atlas Docs — buscador y visor de documentos técnicos

Aplicación Full Stack para cargar TXT, Markdown y PDF con metadatos, procesarlos en segundo plano, buscar sobre título/metadatos/contenido y leerlos sin descargarlos. Implementa PostgreSQL Full-Text Search con índice GIN —sin `LIKE`— y notificaciones SSE sin polling.

## Inicio rápido

Requisitos: Docker Desktop con Docker Compose.

```powershell
docker compose up --build
```

Cuando los servicios estén saludables:

- aplicación: <http://localhost:3000>
- OpenAPI: <http://localhost:8000/docs>
- salud: <http://localhost:8000/health>
- métricas Prometheus: <http://localhost:8000/metrics>

El perfil opcional de observabilidad levanta Prometheus y un dashboard Grafana aprovisionado:

```powershell
docker compose --profile observability up -d
```

- Prometheus: <http://localhost:9090>
- Grafana: <http://localhost:3001> (`admin` / `admin`, sólo para la demo local)

No es necesario crear `.env` para la demo; `compose.yml` incluye valores locales seguros por defecto. Para personalizarlos:

```powershell
Copy-Item .env.example .env
```

## Demostración sugerida

1. Abre **Cargar** y selecciona uno o varios archivos, por ejemplo `samples/architecture-guide.md`.
2. Completa título, autor, categoría, etiquetas y versión.
3. Comprueba que la API responde `PROCESSING` y que la UI cambia a `INDEXED` mediante SSE, sin refrescar.
4. Busca `arquitectura pagos`, revisa tiempo, ranking y resaltado.
5. Abre el resultado y muestra el contenido y sus metadatos en el visor.

También puede cargarse por API:

```powershell
$response = Invoke-RestMethod `
  -Uri http://localhost:8000/api/documents `
  -Method Post `
  -Form @{
    file = Get-Item .\samples\architecture-guide.md
    title = 'Arquitectura de pagos'
    author = 'Equipo de Plataforma'
    category = 'Arquitectura'
    tags = '["backend","pagos","redis"]'
    version = '1.0'
  }

$response
```

## API principal

| Método | Ruta | Uso |
|---|---|---|
| `POST` | `/api/documents` | Carga multipart; devuelve `202 PROCESSING` |
| `POST` | `/api/documents/batch` | Lote con metadata por archivo, `batch_id` y éxito parcial |
| `GET` | `/api/documents/{id}/events` | Stream SSE de `INDEXED`/`ERROR` |
| `GET` | `/api/documents/{id}/status` | Estado durable para diagnóstico |
| `GET` | `/api/documents/search?q=...&page=1&page_size=10` | FTS paginado y resaltado |
| `GET` | `/api/documents/{id}` | Contenido y metadatos para el visor |

El tamaño máximo predeterminado es 10 MB. Los formatos permitidos son `.txt`, `.md` y `.pdf` con texto extraíble.

## Verificación

Pruebas unitarias, contratos e integración real con PostgreSQL, Redis, worker,
SSE y DLQ:

```powershell
docker compose --profile test run --rm tests
```

El servicio efímero de migraciones se ejecuta antes de API y worker. Las
migraciones aplicadas se registran en `schema_migrations`.

Smoke test del flujo completo:

```powershell
.\scripts\smoke.ps1
```

Build del frontend:

```powershell
docker compose build frontend
```

Benchmark de búsqueda, con el stack en ejecución y al menos un documento indexado:

```powershell
py .\scripts\benchmark_search.py --query arquitectura --requests 100 --concurrency 10
```

El reporte muestra media, p50, p95, p99 y falla con código distinto de cero si p95 supera 1000 ms. Una respuesta menor a 400 ms se considera mejor que el objetivo; no se agrega demora artificial.

## Estructura

```text
backend/app/api/     contratos HTTP, DTO y composición de dependencias
backend/app/domain/  entidades, estados y reglas puras
backend/app/application/ casos de uso de carga, búsqueda y procesamiento
backend/app/ports/   protocolos requeridos por los casos de uso
backend/app/infrastructure/ adaptadores PostgreSQL, Redis, disco y métricas
backend/app/workers/ consumidores y orquestación asíncrona
backend/db/          SQL de inicialización de PostgreSQL
backend/db/migrations/ cambios de esquema versionados e idempotentes
frontend/            React + Vite, carga, búsqueda, paginación y visor
docs/architecture.md decisiones, flujo, resiliencia y escalabilidad
docs/ia.md           uso obligatorio y transparente de IA
scripts/             benchmark reproducible
samples/             documento pequeño para la demo
observability/       Prometheus y dashboard Grafana opcionales
compose.yml          entorno unificado
```

## Decisiones clave

- **PostgreSQL FTS:** está permitido por la prueba, mantiene una única fuente de verdad y ofrece índice invertido GIN, ranking y `ts_headline`.
- **Redis Streams:** consumer group, ACK, reintentos, recuperación de pendientes y dead-letter stream con menor costo operativo que Kafka para este alcance.
- **SSE:** el flujo requerido es servidor → navegador; WebSocket añadiría complejidad sin beneficio funcional.
- **Worker separado:** parsing e indexación nunca bloquean la respuesta HTTP de carga.
- **Dependencias hacia adentro:** los casos de uso no conocen FastAPI,
  PostgreSQL, Redis ni almacenamiento local; reciben puertos pequeños y se
  prueban con dobles simples.
- **Trazabilidad durable:** `correlation_id` y `batch_id` viajan por respuesta,
  PostgreSQL, Redis Streams, logs y SSE, incluso después de una reconexión.

Si los puertos predeterminados están ocupados por otro proyecto, pueden
configurarse sin modificar Compose:

```powershell
$env:DOCSEARCH_BACKEND_PORT = '18000'
$env:DOCSEARCH_FRONTEND_PORT = '13000'
docker compose up --build
```

El detalle y los caminos de evolución a Kafka/OpenSearch, almacenamiento de objetos y búsqueda híbrida están en [docs/architecture.md](docs/architecture.md). La declaración de IA está en [docs/ia.md](docs/ia.md).

## Limitaciones conocidas

- Los PDF escaneados sin capa de texto requieren OCR, fuera del alcance actual.
- No se implementó autenticación; para producción se propone OIDC/JWT y RBAC.
- Redis Pub/Sub no conserva notificaciones, por eso el estado durable vive en PostgreSQL y el SSE siempre entrega un snapshot inicial.

## Reinicio limpio del entorno

Sólo si se desea eliminar todos los documentos y datos locales de la demo:

```powershell
docker compose down -v
```
