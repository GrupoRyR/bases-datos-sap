-- Grupos de artículos de SAP Business One.
-- Conjunto MAESTROS, parte grupos_articulos (docs/contrato-robot.md §5).
-- Tabla de origen: OITB.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- Los alias son los nombres de columna del contrato (§5.2). Catálogo sin bandera
-- de activo: activo siempre es Y (contrato §5.1).
SELECT
    T0."ItmsGrpCod"                                 AS "codigo",
    T0."ItmsGrpNam"                                 AS "nombre",
    'Y'                                             AS "activo"
FROM "OITB" T0
ORDER BY T0."ItmsGrpCod"
