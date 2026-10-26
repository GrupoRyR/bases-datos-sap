-- Precios por artículo y lista de precios.
-- Conjunto MAESTROS, parte precios (docs/contrato-robot.md §5).
-- Tablas de origen: ITM1 (precio por artículo y lista), unida a OPLN (listas).
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS: sin
-- parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- Trae todas las listas: el robot se queda con la lista PÚBLICA de cada empresa por
-- su número (HANA_SGX_LISTA_PRECIOS y HANA_SDC_LISTA_PRECIOS; consultas.sql_lista_precios).
-- Para verla a mano, agrega WHERE T0."PriceList" = <número> antes del ORDER BY.
-- Los alias son los nombres de columna del contrato (§5.2). Sin bandera de
-- activo: activo siempre es Y (contrato §5.1).
-- VALIDAR CON DATOS REALES: el número de la lista PÚBLICA de cada empresa en OPLN
-- (SEGUREX: 1, «LISTA PUBLICO»; HBT_SDERIVADOS: sin definir). robot --diagnostico
-- guarda las listas de OPLN.
SELECT
    T0."ItemCode"                                   AS "articulo_codigo",
    T0."PriceList"                                  AS "lista_codigo",
    T1."ListName"                                   AS "lista_nombre",
    T0."Price"                                      AS "precio",
    T0."Currency"                                   AS "moneda",
    'Y'                                             AS "activo"
FROM "ITM1" T0
INNER JOIN "OPLN" T1 ON T0."PriceList" = T1."ListNum"
ORDER BY T0."ItemCode", T0."PriceList"
