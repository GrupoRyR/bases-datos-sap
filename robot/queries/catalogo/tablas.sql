-- Catálogo: todas las tablas del esquema de la empresa con filas y tamaño.
-- Va a la carpeta _CATALOGO (plan §5); nunca se envía a la API.
-- Vista de origen: SYS.M_TABLES (vista de monitoreo de HANA, no una tabla de SAP).
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros; CURRENT_SCHEMA es el esquema que pone la conexión.
-- VALIDAR CON DATOS REALES: que el usuario de HANA del robot pueda leer M_TABLES y
-- que TABLE_SIZE venga en bytes.
SELECT
    T0."TABLE_NAME",
    T0."RECORD_COUNT",
    T0."TABLE_SIZE",
    T0."IS_COLUMN_TABLE"
FROM "SYS"."M_TABLES" T0
WHERE T0."SCHEMA_NAME" = CURRENT_SCHEMA
ORDER BY T0."TABLE_SIZE" DESC
