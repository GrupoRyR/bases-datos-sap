-- Archivo: normas de reparto (OOCR).
-- Carpeta CONTABILIDAD (plan §5), foto completa cada domingo (aaaa-mm-dd.csv, 52 semanas).
-- Solo va a la carpeta BASES_SAP_CSV_DIR; nunca se envía a la API.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- VALIDAR CON DATOS REALES: columnas tomadas de la documentación de SAP B1; confirmarlas con _CATALOGO\<empresa>\columnas antes de la primera extracción.
SELECT
    T0."OcrCode",
    T0."OcrName",
    T0."OcrTotal",
    T0."Direct",
    T0."Active",
    T0."DimCode"
FROM "OOCR" T0
ORDER BY T0."OcrCode"
