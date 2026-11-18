-- Despiece maestro de BEAS (lista de materiales), Segurex, contrato §12
-- Conjunto PRODUCCION, parte "produccion_despiece". Solo SEGUREX. Maestro: la API
-- reemplaza todas las filas en cada corrida.
-- Copia de DESPIECE_MAESTRO_SGX.sql del tablero "Produccion mes a mes"
-- (OneDrive\Claude\automatizacion-hana\tablero-produccion-sgx\consultas), con los
-- nombres del contrato. Todas las lineas de BEAS_STL (3.486 al hacer el tablero):
--   padre     el articulo que se fabrica
--   hijo      el componente
--   cantidad  cuantas unidades del hijo lleva una unidad del padre
--   merma     hoy en cero en todas las lineas; se trae igual para que el dia que la
--             carguen el panel la tome sin cambios
-- Hay una sola version por despiece y ninguna linea con cantidad en cero.
--
-- VALIDAR CON DATOS REALES: que padre + hijo no se repita. Si no se repite, pasa a
-- ser la llave de la parte; hasta entonces va sin llave.
SELECT
    S."ItemCode"                                            AS "padre",
    S."ART1_ID"                                             AS "hijo",
    S."MENGE_VERBRAUCH"                                     AS "cantidad",
    S."AUSSCHUSS"                                           AS "merma"
FROM "BEAS_STL" S
ORDER BY S."ItemCode", S."ART1_ID"
