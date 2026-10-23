# Módulo Sap

Los datos de SAP y todo lo que los mueve: los conjuntos MAESTROS y CARTERA, la recepción de lo que envía el robot (corridas y lotes), las solicitudes de actualización y la API que llaman las apps.

| Qué | Valor |
|---|---|
| Dueña | Sesión «Datos y API» |
| Rutas web | `/sap/*`, nombres `sap.*` |
| Rutas API | `/api/sap/*`, nombres `sap.api.*` |
| Migraciones | `2026_11_02_*` |
| Conexiones | `maestros` y `cartera` para las tablas de cada conjunto; `app` para el resto (solicitudes, corridas, lotes) |
| Puede usar | Contratos de Core |

Lo que Panel necesite leer de aquí lo publica Sap en `App\Modules\Sap\Contracts`. El contrato con el robot está en `docs/contrato-robot.md` y no cambia sin avisarle al usuario.

Las reglas completas están en `docs/arquitectura.md`.
