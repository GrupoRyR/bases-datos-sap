-- Rutas maestras de BEAS (hojas de operaciones), Segurex, contrato §12
-- Conjunto PRODUCCION, parte "produccion_rutas". Solo SEGUREX. Maestro: la API
-- reemplaza todas las filas en cada corrida.
-- Copia de RUTAS_MAESTRAS_SGX.sql del tablero "Produccion mes a mes"
-- (OneDrive\Claude\automatizacion-hana\tablero-produccion-sgx\consultas), con los
-- nombres del contrato. Todas las operaciones de BEAS_APL (1.264 al hacer el
-- tablero), con su puesto en BEAS_APLATZ:
--   area           GRUPPE del puesto, la SECCION: el mismo campo de la carga de planta
--   puesto         el puesto de trabajo concreto
--   tiempo         tiempo de la operacion para "cantidad_base"
--   cantidad_base  el tiempo unitario es tiempo / cantidad_base
--   factor_merma   factor de merma de la operacion
-- Ninguna operacion esta sin puesto. La ruta del propio producto terminado cuenta:
-- es la que aporta ENSAMBLE. PROCESO EXTERNO es una seccion que nunca reporta
-- produccion (trabajo tercerizado).
--
-- VALIDAR CON DATOS REALES: que codigo_articulo + operacion no se repita. Si no se
-- repite, pasa a ser la llave de la parte; hasta entonces va sin llave. Y que POS_ID
-- sea entero.
SELECT
    R."ItemCode"                                            AS "codigo_articulo",
    R."POS_ID"                                              AS "operacion",
    A."GRUPPE"                                              AS "area",
    A."BEZ"                                                 AS "puesto",
    R."TEAPLATZ"                                            AS "tiempo",
    R."MENGE_JE"                                            AS "cantidad_base",
    R."AUSSCHUSSFAKTOR"                                     AS "factor_merma"
FROM "BEAS_APL" R
LEFT JOIN "BEAS_APLATZ" A ON A."APLATZ_ID" = R."APLATZ_ID"
ORDER BY R."ItemCode", R."POS_ID"
