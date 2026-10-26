-- Direcciones de facturación (B) y de envío (S) de clientes y proveedores.
-- Conjunto MAESTROS, parte direcciones (docs/contrato-robot.md §5).
-- Tablas de origen: CRD1, unida a OCRD para quedarse con clientes y proveedores.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- Los alias son los nombres de columna del contrato (§5.2). El robot se queda
-- solo con las direcciones de los socios que envía en la corrida (filtro por
-- codigo_socio, robot/etl/consultas.py).
-- VALIDAR CON DATOS REALES: que cambiar una dirección mueva OCRD.UpdateDate del socio;
-- si no lo mueve, una corrida de cambios no trae la dirección nueva.
SELECT
    T0."CardCode"                                   AS "codigo_socio",
    T0."AdresType"                                  AS "tipo",
    T0."Address"                                    AS "nombre",
    T0."Street"                                     AS "calle",
    T0."Block"                                      AS "barrio",
    T0."City"                                       AS "ciudad",
    -- VALIDAR CON DATOS REALES: que CRD1.County guarde el código del municipio
    -- (el Code de @HBT_MUNICIPIO) y no su nombre.
    T0."County"                                     AS "municipio_codigo",
    T0."State"                                      AS "departamento",
    T0."Country"                                    AS "pais",
    T0."ZipCode"                                    AS "codigo_postal"
FROM "CRD1" T0
INNER JOIN "OCRD" T1 ON T1."CardCode" = T0."CardCode"
WHERE T1."CardType" IN ('C', 'S')
ORDER BY T0."CardCode", T0."AdresType", T0."Address"
