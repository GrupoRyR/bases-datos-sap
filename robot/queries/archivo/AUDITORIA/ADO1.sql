-- Archivo: historial de cambios de líneas de documentos (ADO1).
-- Carpeta AUDITORIA (plan §5), registro: cada noche se suman los días nuevos por la columna UpdateDate (aaaa-mm.csv, no se borra).
-- Solo va a la carpeta BASES_SAP_CSV_DIR; nunca se envía a la API.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- VALIDAR CON DATOS REALES: columnas tomadas de la documentación de SAP B1; confirmarlas con _CATALOGO\<empresa>\columnas antes de la primera extracción.
-- La fecha del cambio sale de ADOC (misma instancia del historial).
-- Tabla grande: solo se extrae con BASES_SAP_ARCHIVO_HISTORIAL_DOCUMENTOS activo,
-- después de ver su tamaño en _CATALOGO (plan §5).
SELECT
    T0."ObjType",
    T0."DocEntry",
    T0."LogInstanc",
    T0."LineNum",
    T0."ItemCode",
    T0."Quantity",
    T0."Price",
    T0."LineTotal",
    T1."UpdateDate"
FROM "ADO1" T0
INNER JOIN "ADOC" T1 ON T1."ObjType" = T0."ObjType" AND T1."DocEntry" = T0."DocEntry" AND T1."LogInstanc" = T0."LogInstanc"
ORDER BY T0."ObjType", T0."DocEntry", T0."LogInstanc", T0."LineNum"
