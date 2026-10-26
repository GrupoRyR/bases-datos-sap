-- Archivo: columnas de las tablas del add-on HBT (@HBT_*), en orden.
-- Trae las columnas de todas las tablas @HBT a la vez (sin parámetros); el robot
-- las agrupa por tabla en Python, salta las que parecen claves y arma con ellas
-- un SELECT con cada columna entre comillas (robot/etl/archivo.py).
-- Vista de origen: SYS.TABLE_COLUMNS (diccionario de HANA, no una tabla de SAP).
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros; CURRENT_SCHEMA es el esquema que pone la conexión.
-- VALIDAR CON DATOS REALES: que el usuario de HANA del robot pueda leer TABLE_COLUMNS.
SELECT
    T0."TABLE_NAME",
    T0."COLUMN_NAME",
    T0."POSITION"
FROM "SYS"."TABLE_COLUMNS" T0
WHERE T0."SCHEMA_NAME" = CURRENT_SCHEMA
  AND T0."TABLE_NAME" LIKE '@HBT%'
ORDER BY T0."TABLE_NAME", T0."POSITION"
