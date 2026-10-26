-- Archivo: historial de cambios de asientos (AJDT).
-- Carpeta AUDITORIA (plan §5), registro: cada noche se suman los días nuevos por la columna UpdateDate (aaaa-mm.csv, no se borra).
-- Solo va a la carpeta BASES_SAP_CSV_DIR; nunca se envía a la API.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- VALIDAR CON DATOS REALES: columnas tomadas de la documentación de SAP B1; confirmarlas con _CATALOGO\<empresa>\columnas antes de la primera extracción.
-- Tabla grande: solo se extrae con BASES_SAP_ARCHIVO_HISTORIAL_DOCUMENTOS activo,
-- después de ver su tamaño en _CATALOGO (plan §5).
SELECT
    T0."TransId",
    T0."LogInstanc",
    T0."RefDate",
    T0."TransType",
    T0."BaseRef",
    T0."Memo",
    T0."UserSign",
    T0."UpdateDate"
FROM "AJDT" T0
ORDER BY T0."TransId", T0."LogInstanc"
