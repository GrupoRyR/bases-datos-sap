-- Precios de la lista PÚBLICA de HBT_SDERIVADOS.
-- Conjunto MAESTROS, parte precios (docs/contrato-robot.md §5).
-- Tablas de origen: ITM1 (precio por artículo y lista), unida a OPLN (listas).
-- Corre tal cual en el Query Manager de SAP B1 en el esquema HBT_SDERIVADOS: sin parámetros
-- y con nombres de tabla sin esquema (lo pone la conexión). Hay un archivo por
-- esquema porque el nombre de la lista puede ser distinto en cada empresa.
-- Los alias son los nombres de columna del contrato (§5.2). Sin bandera de
-- activo: activo siempre es Y (contrato §5.1).
-- VALIDAR CON DATOS REALES: el nombre exacto de la lista PÚBLICA en OPLN de HBT_SDERIVADOS
-- (tilde, mayúsculas, espacios); robot --diagnostico guarda las listas de OPLN. Si
-- dos listas se llaman igual, el robot falla por llave repetida.
SELECT
    T0."ItemCode"                                   AS "articulo_codigo",
    T0."PriceList"                                  AS "lista_codigo",
    T1."ListName"                                   AS "lista_nombre",
    T0."Price"                                      AS "precio",
    T0."Currency"                                   AS "moneda",
    'Y'                                             AS "activo"
FROM "ITM1" T0
INNER JOIN "OPLN" T1 ON T0."PriceList" = T1."ListNum"
WHERE T1."ListName" = 'PÚBLICA'
ORDER BY T0."ItemCode"
