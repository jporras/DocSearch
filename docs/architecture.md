# Arquitectura

## Objetivo y decisiones

La solución prioriza el camino crítico evaluado: recibir documentos de forma asíncrona, indexarlos y responder búsquedas full-text en menos de un segundo. Se eligió una arquitectura modular inspirada en Clean/Hexagonal: separa reglas, casos de uso, puertos y adaptadores sin multiplicar servicios innecesarios.

Principios que gobiernan las decisiones:

- PostgreSQL es la fuente durable de verdad y el motor FTS.
- La búsqueda documental usa `tsvector`, `tsquery` e índice GIN; nunca
  `LIKE`/`ILIKE`.
- La carga responde `202` sin esperar extracción/indexación; el procesamiento
  pesado ocurre en el worker y la búsqueda síncrona no pasa por Redis.
- Redis Streams transporta trabajo durable y Pub/Sub solo señales de baja
  latencia.
- SSE resuelve el flujo servidor → navegador sin introducir WebSockets.
- Una tecnología opcional solo se incorpora si resuelve un problema medido y
  puede sustentarse.

```mermaid
flowchart LR
    UI[Navegador · React] <-->|REST + SSE| NX[Nginx]
    NX --> API[FastAPI]
    API -->|metadatos y consulta| PG[(PostgreSQL)]
    API -->|XADD| RS[(Redis Streams)]
    RS -->|consumer group| W[Worker]
    W -->|extrae TXT/MD/PDF| FS[(Volumen de archivos)]
    W -->|contenido + estado| PG
    W -->|Pub/Sub| RPS[(Redis Pub/Sub)]
    RPS --> API
    MIG[Servicio de migraciones] --> PG
    PM[Prometheus] -->|scrape| API
    PM -->|scrape :9101| W
    GF[Grafana] -->|consulta| PM
```

| Componente | Responsabilidad implementada |
|---|---|
| React + Vite | Carga individual/masiva, búsqueda, seguimiento y visor |
| Nginx | Servir React, reverse proxy, límite de request, rate limit y SSE sin buffering |
| FastAPI | Contratos HTTP, DTO, traducción de errores y SSE |
| PostgreSQL | Metadatos, contenido, estados, trazabilidad y FTS/GIN |
| Redis Streams | Cola durable, consumer group, ACK, pending, retries y DLQ |
| Redis Pub/Sub | Señal de estado hacia las conexiones SSE |
| Worker | Extracción, actualización de estado y publicación de eventos |
| Volumen local | Archivo original compartido por API y worker en el host Compose |
| Prometheus/Grafana | Métricas y visualización operativa |

## Arquitectura interna y dirección de dependencias

```mermaid
flowchart LR
    ROUTES[api · rutas y DTO] --> APP[application · casos de uso]
    ROUTES --> PORTS[ports · protocolos]
    WORKERS[workers] --> APP
    APP --> DOMAIN[domain · reglas puras]
    APP --> PORTS
    INFRA[infrastructure · adaptadores] -. implementa .-> PORTS
    COMPOSE[api/dependencies · composition root] --> APP
    COMPOSE --> INFRA
    WORKERS --> INFRA
```

- `domain/`: estados, metadatos y reglas puras; no conoce FastAPI, Redis,
  PostgreSQL ni filesystem.
- `application/`: casos de uso de carga, consulta y procesamiento; coordina
  puertos y define compensaciones, pero no instancia adaptadores.
- `ports/`: protocolos pequeños exigidos por los casos de uso. No contiene
  repositorios genéricos ni interfaces sin consumidor.
- `infrastructure/`: adaptadores concretos de PostgreSQL, Redis, disco,
  extracción, configuración y métricas.
- `api/`: DTO, validación HTTP, traducción de errores y dependencias. El
  ensamblaje de casos de uso con adaptadores se concentra en
  `api/dependencies.py`.
- `workers/`: consumidor de Redis Streams y composición del caso de uso de
  procesamiento.

La regla es que `domain` y `application` nunca importen infraestructura. Esto
permite probar las reglas y la orquestación con dobles pequeños, mientras las
pruebas de integración se reservan para PostgreSQL, Redis y SSE. La separación
aplica inversión de dependencias donde existe una razón concreta de prueba o
evolución; no intenta convertir cada función en una interfaz.

## Flujo de carga y tiempo real

1. FastAPI valida el contrato y los metadatos; el adaptador de almacenamiento
   valida extensión, tamaño, firma básica y contenido binario.
2. Guarda el archivo con un UUID interno, calcula SHA-256 y registra `PROCESSING`, `correlation_id` y el `batch_id` opcional en PostgreSQL.
3. Publica un evento versionado en Redis Streams y responde `202` inmediatamente.
4. El worker extrae el texto y actualiza el documento. El trigger de PostgreSQL construye el `tsvector`.
5. El worker conserva la correlación durante reintentos y DLQ, publica `INDEXED` o `ERROR`; FastAPI retransmite el evento por SSE y React actualiza la vista sin polling.

La carga masiva acepta metadata por elemento y devuelve un resultado por
archivo. Un elemento inválido queda `REJECTED` sin revertir los aceptados. El
frontend abre una suscripción SSE por cada documento en `PROCESSING`. Los
límites predeterminados son 20 archivos, 50 MB por lote y 10 MB por archivo;
son configurables mediante variables de entorno. Nginx admite 55 MB para el
lote y el overhead multipart; elevar el límite de aplicación requiere ajustar
también `client_max_body_size`.

```mermaid
sequenceDiagram
    actor U as Usuario
    participant FE as React
    participant API as FastAPI
    participant FS as Volumen local
    participant PG as PostgreSQL
    participant RS as Redis Streams
    participant W as Worker
    participant RP as Redis Pub/Sub

    U->>FE: Selecciona archivo(s) y metadatos
    FE->>API: POST /api/documents o /api/documents/batch
    API->>API: Validar contrato y metadatos
    API->>FS: Validar contenido y guardar con UUID
    API->>PG: Crear PROCESSING + trazabilidad
    API->>RS: XADD document.process
    alt publicación confirmada
        API-->>FE: 202 + ID + correlation_id/batch_id
    else Redis no disponible
        API->>PG: Marcar ERROR
        API->>FS: Eliminar archivo compensado
        API-->>FE: 503 o error por elemento
    end
    FE->>API: GET /api/documents/{id}/events
    API->>PG: Leer snapshot durable
    API-->>FE: SSE snapshot PROCESSING/terminal
    RS-->>W: Mensaje del consumer group
    W->>FS: Leer archivo
    W->>W: Extraer texto
    W->>PG: Persistir contenido + INDEXED
    W->>RP: Publicar estado y trazabilidad
    W->>RS: XACK + XDEL
    RP-->>API: Evento de estado
    API-->>FE: SSE INDEXED/ERROR
```

```mermaid
stateDiagram-v2
    [*] --> REJECTED: validación previa fallida
    [*] --> PROCESSING: carga aceptada
    PROCESSING --> PROCESSING: retry
    PROCESSING --> INDEXED: extracción exitosa
    PROCESSING --> ERROR: cola no disponible o intentos agotados
    REJECTED --> [*]
    INDEXED --> [*]
    ERROR --> [*]
```

Redis Streams se eligió en lugar de una lista simple porque ofrece consumer groups, ACK, recuperación de mensajes pendientes y una DLQ. Kafka sería apropiado si existieran múltiples dominios consumidores, replay prolongado o un volumen que justificara su costo operativo. Para el alcance de un día, Streams cubre el problema con menos infraestructura.

```mermaid
flowchart LR
    API[FastAPI] -->|XADD intento 1| STREAM[(Redis Stream)]
    STREAM --> CG[Consumer Group]
    CG --> W[Worker]
    W -. caída antes del ACK .-> PENDING[Pending sin ACK]
    PENDING -->|XAUTOCLAIM tras 60 s| W
    W --> OK{Resultado}
    OK -->|éxito| ACK[XACK + XDEL]
    OK -->|fallo e intento menor a 3| RETRY[XADD intento siguiente]
    RETRY --> ACK
    RETRY --> STREAM
    OK -->|tercer fallo| DLQ[(Dead-letter Stream)]
    DLQ --> ERROR[Documento ERROR]
    ERROR --> ACK
```

## Búsqueda

PostgreSQL es la fuente de verdad y también el motor permitido por la prueba. Un trigger genera un `tsvector` ponderado:

- título: peso A;
- autor, categoría, etiquetas y versión: peso B;
- contenido: peso C.

Un índice GIN evita barridos completos. La consulta utiliza `websearch_to_tsquery`, `@@`, `ts_rank_cd` y `ts_headline`; no usa `LIKE`. La búsqueda es síncrona y no pasa por la cola. La API devuelve paginación, total, ranking, fragmentos resaltados y tiempo medido.

```mermaid
sequenceDiagram
    actor U as Usuario
    participant FE as React
    participant API as FastAPI
    participant PG as PostgreSQL FTS

    U->>FE: Ingresa términos
    FE->>API: GET /api/documents/search?q=...
    API->>PG: websearch_to_tsquery + @@ sobre GIN
    PG-->>API: ranking + ts_headline + total
    API-->>FE: resultados paginados + elapsed_ms
    FE-->>U: Resultados y resaltado
```

El SLA se interpreta como un máximo de un segundo: no se agrega latencia artificial cuando una búsqueda responde en menos de 400 ms. `scripts/benchmark_search.py` reporta p50, p95 y p99; el criterio automatizado exige p95 menor o igual a 1000 ms.

## Errores y resiliencia

- Validaciones retornan `422`; recursos inexistentes, `404`; errores no controlados, un contrato `500` sin filtrar detalles internos.
- Una redelivery posterior a `INDEXED` se convierte en no-op. Esto evita el
  reprocesamiento secuencial, pero no sustituye un lock ante dos entregas
  concurrentes del mismo documento.
- Un mensaje sin ACK por caída del worker puede ser reclamado tras 60 segundos.
- Cada trabajo admite tres intentos; al agotarlos pasa a `documents:dead-letter` y el documento queda `ERROR`.
- Un servicio efímero aplica migraciones versionadas antes de iniciar API y
  worker, y registra cada archivo en `schema_migrations`.
- PostgreSQL conserva el estado fuente de verdad. Redis sólo transporta trabajos y notificaciones.

La creación en PostgreSQL y el `XADD` en Redis constituyen un dual write. Si
Redis rechaza la publicación, el caso de uso marca el documento `ERROR` y
elimina el archivo. Persiste una ventana de caída entre el commit y el envío;
un outbox transaccional es la evolución prevista si se exige entrega sin esa
ventana. Esta limitación no se oculta durante la sustentación.

## Seguridad

```mermaid
flowchart LR
    CLIENT[Cliente] --> NX[Nginx · límites y rate limit]
    NX --> API[FastAPI · contrato y metadatos]
    API --> FV[Storage · extensión, tamaño y firma]
    FV --> FS[(Archivo con UUID fuera del directorio público)]
    API --> DB[(Consultas parametrizadas)]
```

- Lista explícita TXT/MD/PDF, máximo configurable y revisión de firma `%PDF`/contenido binario.
- Nombres de almacenamiento UUID y archivos fuera del directorio público.
- SHA-256 para trazabilidad y futura deduplicación.
- Consultas parametrizadas con psycopg.
- Nginx aplica límite de tamaño y rate limiting.
- CORS se configura por ambiente.

Autenticación y antivirus quedan fuera del alcance funcional. En producción se integrarían OIDC/JWT con roles `ADMIN`/`USER` y un escáner como ClamAV antes de publicar el trabajo.

## Relación con los criterios de evaluación

- **Código limpio:** responsabilidades separadas, nombres orientados al caso de
  uso y un único composition root HTTP.
- **SOLID/DRY:** SRP separa rutas, casos de uso y adaptadores; DIP hace que la
  aplicación dependa de puertos; ISP mantiene protocolos pequeños y DRY
  concentra reglas y compensaciones sin repositorios genéricos.
- **Seguridad y validaciones:** la API valida metadatos y el adaptador de
  almacenamiento valida extensión, tamaño, firma y contenido básico.
- **Sustentación:** cada adaptador responde a una necesidad del flujo y puede
  sustituirse sin alterar el contrato REST.
- **Pruebas unitarias:** los casos de uso se prueban sin PostgreSQL, Redis o
  filesystem real; las integraciones reales complementan esa cobertura.

## Escalabilidad

- API, frontend y workers pueden replicarse dentro de un mismo host que
  comparta el volumen de archivos.
- Redis consumer groups distribuye documentos entre workers.
- PostgreSQL puede incorporar réplicas de lectura y particionamiento; el índice GIN mantiene la consulta indexada.
- Para escalar entre nodos, los archivos deben migrar del volumen local a
  S3/MinIO o a otro almacenamiento compartido detrás del puerto existente.
- Si la carga supera la capacidad de PostgreSQL FTS, el puerto de búsqueda puede implementarse con OpenSearch/Elasticsearch sin cambiar el contrato REST.

## Observabilidad

`/metrics` expone métricas Prometheus de tasa y latencia HTTP, histograma específico de búsqueda, cargas aceptadas y longitud del stream. El worker expone en el puerto interno `9101` duración de procesamiento, resultados, reintentos, DLQ y mensajes pendientes. El perfil opcional `observability` levanta Prometheus y un dashboard Grafana aprovisionado con estas señales. Los logs del worker incluyen documento, correlación, lote, intento y errores de extracción.

## Evidencia de verificación

La suite ejecutada dentro de Compose contiene 18 pruebas unitarias/de contrato
y 3 pruebas de integración, con resultado verificado de `21 passed`. Las
integraciones recorren PostgreSQL, Redis Streams, worker, SSE, FTS, detalle,
reintentos, DLQ y carga masiva con éxito parcial. El build de React y la
validación de Compose se ejecutan por separado.

```mermaid
flowchart LR
    U[Pruebas unitarias] --> UC[Dominio y casos de uso]
    C[Contratos HTTP] --> API[FastAPI]
    I[Integración Compose] --> PG[(PostgreSQL)]
    I --> RS[(Redis)]
    I --> WK[Worker]
    I --> SSE[SSE]
    B[Benchmark] --> FTS[PostgreSQL FTS]
```

## Capacidades opcionales

| Necesidad | Decisión actual | Alternativa | Motivo |
|---|---|---|---|
| Persistencia y FTS | PostgreSQL + GIN | MongoDB/OpenSearch | Una fuente de verdad y menos operación |
| Procesamiento asíncrono | Redis Streams | Kafka | ACK, consumer groups y DLQ con menor costo |
| Tiempo real | SSE | WebSocket | Comunicación principalmente servidor → cliente |
| Archivos | Volumen local detrás de un puerto | S3/MinIO | Simplicidad de demo y sustitución futura |
| Búsqueda vectorial | Fuera del runtime | pgvector | Primero demostrar FTS y medir relevancia |
| RAG/LLM | Fuera del camino obligatorio | Ollama/servicio LLM | No es necesario para cumplir la prueba |

La búsqueda semántica, RAG y Ollama del proyecto de referencia son una evolución válida, pero permanecen fuera del camino obligatorio. Primero se garantiza full-text, visor y tiempo real; después puede añadirse recuperación híbrida (FTS + vectores mediante RRF) como endpoint independiente.

```mermaid
flowchart LR
    Q[Consulta] --> FTS[PostgreSQL FTS · lexical]
    Q -. evolución .-> VEC[pgvector · semántica]
    FTS --> RRF[Fusión RRF]
    VEC -.-> RRF
    RRF --> RESULT[Ranking final]
```
