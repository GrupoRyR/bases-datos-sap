-- Grupos de clientes (el canal) de SAP Business One: OCRG con GroupType = 'C'.
-- Conjunto MAESTROS, parte grupos_clientes (docs/contrato-robot.md §5).
-- Tabla de origen: OCRG.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- Los alias son los nombres de columna del contrato (§5.2). Catálogo sin bandera
-- de activo: activo siempre es Y (contrato §5.1).
SELECT
    T0."GroupCode"                                  AS "codigo",
    T0."GroupName"                                  AS "nombre",
    'Y'                                             AS "activo"
FROM "OCRG" T0
WHERE T0."GroupType" = 'C'
ORDER BY T0."GroupCode"
