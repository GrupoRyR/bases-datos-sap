-- Producto terminado que entra a bodega desde una OT (Segurex), contrato §12
-- Conjunto PRODUCCION, parte "produccion_terminado". Solo SEGUREX.
-- Copia de PT_FAMILIA_SGX.sql del tablero "Produccion mes a mes"
-- (OneDrive\Claude\automatizacion-hana\tablero-produccion-sgx\consultas), con los
-- cambios del §12 y nada mas:
--   * una fila por linea de la entrada (OIGN/IGN1), sin GROUP BY: la suma por dia
--     y articulo da lo mismo que la consulta original;
--   * la ventana de VENTAS en vez del BETWEEN fijo (ver abajo);
--   * los nombres del contrato y ROUND(..., 2) en el valor.
--
-- Llave natural: "doc_entry" + "linea".
--
-- Filtro: linea ligada a una OT de BEAS (U_beas_belnrid > 0) y articulo de un
-- grupo que empieza por PRODUCTO TERMINADO. En producto terminado U_GSP_FAMILIA
-- esta completo; "Sin familia" queda solo como respaldo.
--
-- Ventana sin parametros (corre igual en el Query Manager): el mes en curso mas
-- los ultimos 7 dias del mes anterior, hasta hoy, por la fecha de la entrada.
-- Es la misma expresion de VENTAS y el robot la calcula en HANA como ventana_desde.
--
-- VALIDAR CON DATOS REALES: la consulta original no filtra CANCELED. Revisar si una
-- entrada anulada deja dos filas que se anulan entre si o una sola.
SELECT
    G0."DocEntry"                                              AS "doc_entry",
    G0."DocNum"                                                AS "numero_documento",
    G1."LineNum"                                               AS "linea",
    CAST(G0."DocDate" AS DATE)                                 AS "fecha",
    COALESCE(NULLIF(TRIM(B."ItmsGrpNam"), ''), 'Sin grupo')    AS "grupo",
    COALESCE(NULLIF(TRIM(I."U_GSP_FAMILIA"), ''), 'Sin familia') AS "familia",
    G1."ItemCode"                                              AS "codigo_articulo",
    G1."Dscription"                                            AS "articulo",
    -- VALIDAR CON DATOS REALES: que U_beas_belnrid y U_beas_belposid sean enteros.
    G1."U_beas_belnrid"                                        AS "nro_ot",
    G1."U_beas_belposid"                                       AS "posicion",
    G1."Quantity"                                              AS "cantidad",
    ROUND(G1."LineTotal", 2)                                   AS "valor"
FROM "OIGN" G0
INNER JOIN "IGN1" G1 ON G1."DocEntry" = G0."DocEntry"
LEFT JOIN "OITM" I ON I."ItemCode"   = G1."ItemCode"
LEFT JOIN "OITB" B ON B."ItmsGrpCod" = I."ItmsGrpCod"
WHERE G1."U_beas_belnrid" > 0
  AND UPPER(COALESCE(B."ItmsGrpNam", '')) LIKE 'PRODUCTO TERMINADO%'
  AND CAST(G0."DocDate" AS DATE) >= ADD_DAYS(CURRENT_DATE, -6 - DAYOFMONTH(CURRENT_DATE))
  AND CAST(G0."DocDate" AS DATE) <= CURRENT_DATE
ORDER BY CAST(G0."DocDate" AS DATE), G0."DocEntry", G1."LineNum"
