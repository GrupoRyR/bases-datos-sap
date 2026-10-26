-- Archivo: períodos contables (OFPR).
-- Carpeta CONTABILIDAD (plan §5), foto completa cada domingo (aaaa-mm-dd.csv, 52 semanas).
-- Solo va a la carpeta BASES_SAP_CSV_DIR; nunca se envía a la API.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- VALIDAR CON DATOS REALES: columnas tomadas de la documentación de SAP B1; confirmarlas con _CATALOGO\<empresa>\columnas antes de la primera extracción.
SELECT
    T0."AbsEntry",
    T0."Code",
    T0."Name",
    T0."F_RefDate",
    T0."T_RefDate",
    T0."PeriodStat",
    T0."Category"
FROM "OFPR" T0
ORDER BY T0."AbsEntry"
