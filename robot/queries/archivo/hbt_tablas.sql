-- Archivo: tablas del add-on HBT (@HBT_*) de la empresa, para la carpeta CONFIGURACION.
-- El robot lee cada una con una lista de columnas armada desde hbt_columnas.sql
-- (nunca SELECT de todas las columnas) y salta las que parecen claves.
-- Vista de origen: SYS.TABLES (diccionario de HANA, no una tabla de SAP).
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros; CURRENT_SCHEMA es el esquema que pone la conexión.
-- VALIDAR CON DATOS REALES: que el usuario de HANA del robot pueda leer SYS.TABLES.
SELECT
    T0."TABLE_NAME"
FROM "SYS"."TABLES" T0
WHERE T0."SCHEMA_NAME" = CURRENT_SCHEMA
  AND T0."TABLE_NAME" LIKE '@HBT%'
ORDER BY T0."TABLE_NAME"
