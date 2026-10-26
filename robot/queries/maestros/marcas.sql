-- Marcas (fabricantes) de los artículos de SAP Business One.
-- Conjunto MAESTROS, parte marcas (docs/contrato-robot.md §5).
-- Tabla de origen: OMRC.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- Los alias son los nombres de columna del contrato (§5.2). Catálogo sin bandera
-- de activo: activo siempre es Y (contrato §5.1).
SELECT
    T0."FirmCode"                                   AS "codigo",
    T0."FirmName"                                   AS "nombre",
    'Y'                                             AS "activo"
FROM "OMRC" T0
ORDER BY T0."FirmCode"
