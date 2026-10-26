-- Archivo: historial de cambios de artículos (AITM).
-- Carpeta AUDITORIA (plan §5), registro: cada noche se suman los días nuevos por la columna UpdateDate (aaaa-mm.csv, no se borra).
-- Solo va a la carpeta BASES_SAP_CSV_DIR; nunca se envía a la API.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- VALIDAR CON DATOS REALES: columnas tomadas de la documentación de SAP B1; confirmarlas con _CATALOGO\<empresa>\columnas antes de la primera extracción.
SELECT
    T0."LogInstanc",
    T0."ItemCode",
    T0."ItemName",
    T0."ItmsGrpCod",
    T0."validFor",
    T0."frozenFor",
    T0."UserSign2",
    T0."UpdateDate"
FROM "AITM" T0
ORDER BY T0."ItemCode", T0."LogInstanc"
