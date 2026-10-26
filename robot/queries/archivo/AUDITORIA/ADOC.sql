-- Archivo: historial de cambios de documentos (ADOC).
-- Carpeta AUDITORIA (plan §5), registro: cada noche se suman los días nuevos por la columna UpdateDate (aaaa-mm.csv, no se borra).
-- Solo va a la carpeta BASES_SAP_CSV_DIR; nunca se envía a la API.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- VALIDAR CON DATOS REALES: columnas tomadas de la documentación de SAP B1; confirmarlas con _CATALOGO\<empresa>\columnas antes de la primera extracción.
-- Tabla grande: solo se extrae con BASES_SAP_ARCHIVO_HISTORIAL_DOCUMENTOS activo,
-- después de ver su tamaño en _CATALOGO (plan §5).
SELECT
    T0."ObjType",
    T0."DocEntry",
    T0."DocNum",
    T0."LogInstanc",
    T0."CardCode",
    T0."DocDate",
    T0."DocTotal",
    T0."DocStatus",
    T0."CANCELED",
    T0."UserSign",
    T0."UserSign2",
    T0."UpdateDate"
FROM "ADOC" T0
ORDER BY T0."ObjType", T0."DocEntry", T0."LogInstanc"
