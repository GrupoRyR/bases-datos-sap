-- Catálogo: campos de usuario (U_*) de todas las tablas de la empresa.
-- Va a la carpeta _CATALOGO (plan §5); nunca se envía a la API.
-- Tabla de origen: CUFD.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- VALIDAR CON DATOS REALES: los nombres de columna de CUFD (tomados de la
-- documentación de SAP B1), sobre todo EditSize, Dflt, NotNull y RTable.
SELECT
    T0."TableID",
    T0."FieldID",
    T0."AliasID",
    T0."Descr",
    T0."TypeID",
    T0."EditType",
    T0."SizeID",
    T0."EditSize",
    T0."Dflt",
    T0."NotNull",
    T0."RTable"
FROM "CUFD" T0
ORDER BY T0."TableID", T0."FieldID"
