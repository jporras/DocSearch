# Guía de arquitectura de pagos

## Objetivo

El servicio de pagos procesa órdenes de manera idempotente y publica eventos de dominio para evitar acoplamiento entre conciliación, notificaciones y contabilidad.

## Componentes

- La API valida la orden y genera una clave de idempotencia.
- PostgreSQL conserva el estado transaccional.
- Redis mantiene datos efímeros y límites de frecuencia.
- Los consumidores procesan eventos con reintentos y dead-letter queue.

## Seguridad

Todo acceso requiere autenticación, autorización por rol y trazabilidad. Los secretos se administran fuera del repositorio y los datos sensibles se cifran en tránsito y reposo.
