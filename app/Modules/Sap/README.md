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

## Partes y columnas

`Contracts\Enums\Part` nombra cada parte del contrato (§1, §5 y §6) con su conjunto, su llave y sus columnas (`Domain\Columns\PartColumns`). El valor de cada caso es el nombre del contrato, que es también la tabla (`clientes`) y, con `v_`, la vista (`v_clientes`). Cambiar una columna es cambiar el contrato: primero lo aprueba el usuario.

## Tablas y vistas

| Conjunto | Conexión | Tablas | Vistas |
|---|---|---|---|
| MAESTROS | `maestros` | Una por parte: `clientes`, `proveedores`, `direcciones`, `contactos`, `articulos`, `grupos_articulos`, `marcas`, `precios`, `vendedores`, `grupos_clientes`, `condiciones_pago`, `municipios` | `v_<tabla>` |
| CARTERA | `cartera` | `cartera` (actual) y `cartera_fotos` (una foto por empresa y `fecha_corte`) | `v_cartera`, `v_cartera_fotos` |

- Cada fila de MAESTROS lleva `empresa`, sus columnas del contrato, `activo`, `actualizado_en_sap` (solo la traen clientes, proveedores y artículos), `sincronizado_en` y `corrida_id`. Es única por empresa y llave. Nunca se borra: lo que deja de llegar queda inactivo.
- CARTERA no tiene llave natural: cada cierre bueno reemplaza toda la cartera de la empresa en una transacción.
- Las vistas listan sus columnas una por una y nunca muestran `id` ni `corrida_id`. Para cambiar una vista se agregan columnas al final en una migración nueva; nunca se renombra ni se quita una, porque las apps leen de ellas.
- Los textos van como `varchar` con el largo de SAP; las horas, en hora de Bogotá; los montos, `decimal(19,2)`.
