-- Archivo: ingresos de soporte (OSUL).
-- Carpeta AUDITORIA (plan §5), registro: cada noche se suman los días nuevos por la columna Date (aaaa-mm.csv, no se borra).
-- Solo va a la carpeta BASES_SAP_CSV_DIR; nunca se envía a la API.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- VALIDAR CON DATOS REALES: columnas tomadas de la documentación de SAP B1; confirmarlas con _CATALOGO\<empresa>\columnas antes de la primera extracción.
-- VALIDAR CON DATOS REALES: OSUL es la tabla menos documentada; estas columnas son
-- una suposición. Si no existen, el robot reporta el fallo y sigue con las demás tablas.
SELECT
    T0."UserCode",
    T0."Date",
    T0."Time",
    T0."Action"
FROM "OSUL" T0
ORDER BY T0."Date", T0."Time", T0."UserCode"
