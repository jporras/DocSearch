# Uso de inteligencia artificial

## Herramientas utilizadas

Se utilizó ChatGPT/Codex como asistente de análisis y desarrollo. También se consultó un documento de arquitectura elaborado previamente mediante interacción con ChatGPT. El proyecto `chatbot` existente se usó como referencia local para patrones de FastAPI, procesamiento PDF, SSE, React y observabilidad.

## Casos de uso

- Extracción y organización de los requisitos del PDF suministrado.
- Comparación del alcance obligatorio con la arquitectura RAG existente.
- Generación del esqueleto de backend, frontend, pruebas y documentación.
- Revisión de riesgos: búsqueda sin `LIKE`, latencia, seguridad de archivos, reintentos y DLQ.
- Preparación de un benchmark reproducible y argumentos para la sustentación.

## Prompts clave y refinamiento

Prompts representativos del proceso:

> Crea un proyecto para la prueba técnica usando lo reutilizable del proyecto chatbot y siguiendo los lineamientos del PDF.

> ¿Kafka es necesario para el proceso asíncrono o cuál alternativa propones?

> Identifica qué aspectos adicionales pueden dar más puntos aprovechando que no se parte desde cero.

El primer planteamiento se refinó para separar el camino obligatorio de búsqueda full-text de las capacidades RAG. Kafka se sustituyó por Redis Streams al no requerirse replay prolongado ni múltiples dominios consumidores. La búsqueda se mantuvo en PostgreSQL FTS, opción autorizada expresamente por la prueba, para reducir riesgo operativo.

## Validación humana

Cada propuesta se contrastó con los criterios del PDF. Se revisaron manualmente el esquema SQL, la ausencia de `LIKE`, el contrato REST, el flujo SSE, la configuración Docker y la separación entre estado durable y transporte de eventos. Se añadieron pruebas automatizadas y un script de latencia para evitar aceptar afirmaciones de la IA sin evidencia ejecutable.

Antes de entregar, el candidato debe ejecutar la verificación descrita en el README, revisar los resultados del benchmark en su máquina y ajustar este documento si utiliza herramientas o prompts adicionales.
