-- Archivo: actividades (OCLG).
-- Carpeta VENTAS_Y_CRM (plan §5), foto completa cada domingo (aaaa-mm-dd.csv, 52 semanas).
-- Solo va a la carpeta BASES_SAP_CSV_DIR; nunca se envía a la API.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- VALIDAR CON DATOS REALES: columnas tomadas de la documentación de SAP B1; confirmarlas con _CATALOGO\<empresa>\columnas antes de la primera extracción.
SELECT
    T0."ClgCode",
    T0."CardCode",
    T0."CntctDate",
    T0."Action",
    T0."CntctSbjct",
    T0."Details",
    T0."AttendUser",
    T0."Closed"
FROM "OCLG" T0
ORDER BY T0."ClgCode"
