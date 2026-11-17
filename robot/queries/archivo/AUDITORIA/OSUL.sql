-- Archivo: ingresos de soporte (OSUL).
-- Carpeta AUDITORIA (plan §5), registro: cada noche se suman los días nuevos por la columna StartDate (aaaa-mm.csv, no se borra).
-- Solo va a la carpeta BASES_SAP_CSV_DIR; nunca se envía a la API.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- Columnas confirmadas con _CATALOGO\SEGUREX\columnas el 17/11/2026. Se deja por
-- fuera ChkHash (hash de control del registro, no es información de auditoría).
-- VALIDAR CON DATOS REALES: Derivados (HBT_SDERIVADOS) todavía no se confirmó con su
-- catálogo; corre --archivo registros y revisa el log.
SELECT
    T0."ID",
    T0."RealName",
    T0."LogReason",
    T0."LogDetail",
    T0."Mac",
    T0."Machine",
    T0."StartDate",
    T0."StartTime",
    T0."EndDate",
    T0."EndTime"
FROM "OSUL" T0
ORDER BY T0."StartDate", T0."StartTime", T0."ID"
