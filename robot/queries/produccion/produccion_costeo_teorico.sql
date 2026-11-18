-- Costeo teorico (SOLL) por articulo de producto terminado, Segurex, contrato §12
-- Conjunto PRODUCCION, parte "produccion_costeo_teorico". Solo SEGUREX. Maestro: la
-- API reemplaza todas las filas en cada corrida.
-- Copia de COSTEO_TEORICO_SGX.sql del tablero "Produccion mes a mes"
-- (OneDrive\Claude\automatizacion-hana\tablero-produccion-sgx\consultas), con los
-- nombres del contrato y ROUND(..., 2) en los montos.
--
-- Llave natural: "codigo_articulo".
--
-- SELBSTKOSTEN_GK_SOLL es el costo estandar TOTAL de la posicion de OT, para su
-- MENGE. Dividido por la cantidad da el estandar unitario, que es propiedad del
-- articulo y no del periodo: por eso no se filtra por fecha. Se suma sobre todas las
-- posiciones con cantidad y se parte en los componentes que SAP distingue: MATERIAL
-- (materia prima y piezas adquiridas) y FERTIGUNG (fabricacion: mano de obra, costos
-- variables y fijos).
SELECT
    P."ItemCode"                                            AS "codigo_articulo",
    MAX(P."ItemName")                                       AS "articulo",
    MAX(COALESCE(NULLIF(TRIM(I."U_GSP_FAMILIA"), ''), 'Sin familia')) AS "familia",
    COUNT(*)                                                AS "posiciones",
    SUM(P."MENGE")                                          AS "cantidad",
    ROUND(SUM(P."MATERIAL_GK_SOLL"), 2)                     AS "material_soll",
    ROUND(SUM(P."FERTIGUNG_GK_SOLL"), 2)                    AS "fabricacion_soll",
    ROUND(SUM(P."SELBSTKOSTEN_GK_SOLL"), 2)                 AS "total_soll",
    ROUND(SUM(P."SELBSTKOSTEN_GK_IST"), 2)                  AS "total_ist"
FROM "BEAS_FTPOS" P
LEFT JOIN "OITM" I ON I."ItemCode"   = P."ItemCode"
LEFT JOIN "OITB" B ON B."ItmsGrpCod" = I."ItmsGrpCod"
WHERE UPPER(COALESCE(B."ItmsGrpNam", '')) IN
      ('PRODUCTO TERMINADO SEGUREX', 'PRODUCTO TERMINADO INAFER')
  AND P."MENGE" > 0
GROUP BY P."ItemCode"
ORDER BY SUM(P."MENGE") DESC
