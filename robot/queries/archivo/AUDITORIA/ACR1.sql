-- Archivo: historial de cambios de direcciones de socios (ACR1).
-- Carpeta AUDITORIA (plan §5), registro: cada noche se suman los días nuevos por la columna UpdateDate (aaaa-mm.csv, no se borra).
-- Solo va a la carpeta BASES_SAP_CSV_DIR; nunca se envía a la API.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- VALIDAR CON DATOS REALES: columnas tomadas de la documentación de SAP B1; confirmarlas con _CATALOGO\<empresa>\columnas antes de la primera extracción.
-- La fecha del cambio sale de ACRD (misma instancia del historial).
SELECT
    T0."CardCode",
    T0."LogInstanc",
    T0."Address",
    T0."AdresType",
    T0."Street",
    T0."City",
    T0."County",
    T0."State",
    T0."Country",
    T1."UpdateDate"
FROM "ACR1" T0
INNER JOIN "ACRD" T1 ON T1."CardCode" = T0."CardCode" AND T1."LogInstanc" = T0."LogInstanc"
ORDER BY T0."CardCode", T0."LogInstanc", T0."AdresType", T0."Address"
