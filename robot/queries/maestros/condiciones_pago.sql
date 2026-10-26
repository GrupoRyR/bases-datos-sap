-- Condiciones de pago de SAP Business One.
-- Conjunto MAESTROS, parte condiciones_pago (docs/contrato-robot.md §5).
-- Tabla de origen: OCTG.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- Los alias son los nombres de columna del contrato (§5.2). Catálogo sin bandera
-- de activo: activo siempre es Y (contrato §5.1).
SELECT
    T0."GroupNum"                                   AS "codigo",
    T0."PymntGroup"                                 AS "nombre",
    T0."ExtraDays"                                  AS "dias_extra",
    T0."ExtraMonth"                                 AS "meses_extra",
    'Y'                                             AS "activo"
FROM "OCTG" T0
ORDER BY T0."GroupNum"
