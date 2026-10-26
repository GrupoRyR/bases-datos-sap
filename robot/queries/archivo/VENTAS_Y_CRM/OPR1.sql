-- Archivo: etapas de las oportunidades (OPR1).
-- Carpeta VENTAS_Y_CRM (plan §5), foto completa cada domingo (aaaa-mm-dd.csv, 52 semanas).
-- Solo va a la carpeta BASES_SAP_CSV_DIR; nunca se envía a la API.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- VALIDAR CON DATOS REALES: columnas tomadas de la documentación de SAP B1; confirmarlas con _CATALOGO\<empresa>\columnas antes de la primera extracción.
SELECT
    T0."OpprId",
    T0."Line",
    T0."Step_Id",
    T0."OpenDate",
    T0."CloseDate",
    T0."SlpCode",
    T0."MaxSumLoc",
    T0."ClosePrcnt"
FROM "OPR1" T0
ORDER BY T0."OpprId", T0."Line"
