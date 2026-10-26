-- Archivo: formas de pago (OPYM).
-- Carpeta BANCOS (plan §5), foto completa cada domingo (aaaa-mm-dd.csv, 52 semanas).
-- Solo va a la carpeta BASES_SAP_CSV_DIR; nunca se envía a la API.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- VALIDAR CON DATOS REALES: columnas tomadas de la documentación de SAP B1; confirmarlas con _CATALOGO\<empresa>\columnas antes de la primera extracción.
SELECT
    T0."PayMethCod",
    T0."Descript",
    T0."Type",
    T0."BnkDflt",
    T0."Active"
FROM "OPYM" T0
ORDER BY T0."PayMethCod"
