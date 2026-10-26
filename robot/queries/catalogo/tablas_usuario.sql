-- Catálogo: tablas de usuario (@...) definidas en la empresa.
-- Va a la carpeta _CATALOGO (plan §5); nunca se envía a la API.
-- Tabla de origen: OUTB.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- VALIDAR CON DATOS REALES: los nombres de columna de OUTB (tomados de la
-- documentación de SAP B1), sobre todo TblNum, ObjectType y Archivable.
SELECT
    T0."TableName",
    T0."Descr",
    T0."TblNum",
    T0."ObjectType",
    T0."Archivable"
FROM "OUTB" T0
ORDER BY T0."TableName"
