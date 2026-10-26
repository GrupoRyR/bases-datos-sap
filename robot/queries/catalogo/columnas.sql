-- Catálogo: todas las columnas de todas las tablas del esquema de la empresa.
-- Va a la carpeta _CATALOGO (plan §5); nunca se envía a la API. Sirve para
-- confirmar los nombres marcados VALIDAR en las demás consultas; el robot se queda
-- en Python solo con las tablas que lee.
-- Vista de origen: SYS.TABLE_COLUMNS (diccionario de HANA, no una tabla de SAP).
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros; CURRENT_SCHEMA es el esquema que pone la conexión.
-- VALIDAR CON DATOS REALES: que el usuario de HANA del robot pueda leer TABLE_COLUMNS.
SELECT
    T0."TABLE_NAME",
    T0."POSITION",
    T0."COLUMN_NAME",
    T0."DATA_TYPE_NAME",
    T0."LENGTH",
    T0."SCALE",
    T0."IS_NULLABLE"
FROM "SYS"."TABLE_COLUMNS" T0
WHERE T0."SCHEMA_NAME" = CURRENT_SCHEMA
ORDER BY T0."TABLE_NAME", T0."POSITION"
