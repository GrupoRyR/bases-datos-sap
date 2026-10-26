-- Archivo: sucursales (OBPL).
-- Carpeta ORGANIZACION (plan §5), foto completa cada domingo (aaaa-mm-dd.csv, 52 semanas).
-- Solo va a la carpeta BASES_SAP_CSV_DIR; nunca se envía a la API.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- VALIDAR CON DATOS REALES: columnas tomadas de la documentación de SAP B1; confirmarlas con _CATALOGO\<empresa>\columnas antes de la primera extracción.
SELECT
    T0."BPLId",
    T0."BPLName",
    T0."Disabled",
    T0."TaxIdNum",
    T0."MainBPL"
FROM "OBPL" T0
ORDER BY T0."BPLId"
