-- Costos de produccion por concepto, area y linea (Segurex), contrato §12
-- Conjunto PRODUCCION, parte "produccion_costos". Solo SEGUREX.
-- Copia de COSTOS_PRODUCCION_SGX_MATERIAL.sql del tablero "Produccion mes a mes"
-- (OneDrive\Claude\automatizacion-hana\tablero-produccion-sgx\consultas), con los
-- cambios del §12 y nada mas: la ventana de VENTAS en vez del BETWEEN fijo, los
-- nombres del contrato, ROUND(..., 2) en el costo y NULL en vez de los textos vacios.
-- Una sola adaptacion del robot: la original usa WITH; aqui los hechos de costo se
-- unen primero (UNION ALL) y despues, una sola vez, a los atributos de la posicion
-- de OT. Da las mismas filas, y asi la consulta tambien corre dentro de la
-- subconsulta con que el robot la cuenta (SELECT COUNT(*) FROM (...)).
--
-- Una fila por HECHO DE COSTO. Sin llave: cada reporte da hasta tres filas.
--   Mano de obra directa  BEAS_ARBZEIT.PCOSTVK
--   Costo variable        BEAS_ARBZEIT.KOSTEN_GK
--   Costo fijo            BEAS_ARBZEIT.KOSTEN_VK - KOSTEN_GK
--   Material              OIGE/IGE1, la salida que BEAS genera al descargar el
--                         material a la OT. "Material intermedio" si el articulo
--                         consumido alguna vez fue posicion de una OT (la planta lo
--                         fabrica); si no, "Material comprado".
-- Los tres conceptos de transformacion son los de la consulta "PRODUCCION - OT
-- (Fecha Inicio/Fin)" del Query Manager, tomados ya valorizados de BEAS_ARBZEIT.
--
-- El material no tiene area: BEAS_FTSTL.APLANPOS_ID esta en cero en toda la base,
-- asi que SAP no sabe en que operacion se consumio. Va a "Material comprado (sin
-- area)" o "Material intermedio (sin area)".
--
-- Las filas de "Material intermedio" SI se envian: son piezas que la propia planta
-- fabrico y vuelven a entrar como insumo. El panel las excluye al sumar el costo.
--
-- Se excluyen OIGN (es el producto terminado que sale del proceso, no un costo), los
-- reportes anulados (CANCEL = 1) y las filas de costo cero, como en el tablero.
--
-- "linea_producto" es la regla de dos pasos de produccion_carga_planta.sql, copiada
-- tal cual.
--
-- Ventana sin parametros (corre igual en el Query Manager): el mes en curso mas
-- los ultimos 7 dias del mes anterior, hasta hoy, por la fecha del reporte o de la
-- salida. Es la misma expresion de VENTAS y el robot la calcula en HANA como
-- ventana_desde.
SELECT
    H."Fecha"                                               AS "fecha",
    H."Concepto"                                            AS "concepto",
    H."Area"                                                AS "area",
    CASE
      WHEN TRIM(COALESCE(I."U_GSP_FAMILIA", '')) NOT IN
           ('', 'PIEZAS EN NEGRO', 'PIEZAS TERMINADAS', 'ENSAMBLES')
                                                        THEN TRIM(I."U_GSP_FAMILIA")
      WHEN UPPER(P."ItemName") LIKE '%ULTRA%'           THEN 'C-999 ULTRA'
      WHEN UPPER(P."ItemName") LIKE '%C-999%'
        OR UPPER(P."ItemName") LIKE '%C999%'            THEN 'C-999'
      WHEN UPPER(P."ItemName") LIKE '%JUPITER%'         THEN 'JUPITER'
      WHEN UPPER(P."ItemName") LIKE '%MEGA%'            THEN 'MEGA'
      WHEN UPPER(P."ItemName") LIKE '%SUPRA%'           THEN 'SUPRA'
      WHEN UPPER(P."ItemName") LIKE '%ORBIT%'           THEN 'ORBIT'
      WHEN UPPER(P."ItemName") LIKE '%SATURNO%'         THEN 'SATURNO'
      WHEN UPPER(P."ItemName") LIKE '%BALL%'            THEN 'BALL'
      WHEN UPPER(P."ItemName") LIKE '%B-100%'
        OR UPPER(P."ItemName") LIKE '%B100%'            THEN 'B-100'
      WHEN UPPER(P."ItemName") LIKE '%TIPO B%'          THEN 'TIPO B'
      WHEN UPPER(P."ItemName") LIKE '%TIPO H%'          THEN 'TIPO H'
      WHEN UPPER(P."ItemName") LIKE '%MADERA%'          THEN 'MADERA'
      WHEN UPPER(P."ItemName") LIKE '%ESCUDO%'          THEN 'ESCUDOS'
      WHEN UPPER(P."ItemName") LIKE '%TOPE%'            THEN 'TOPES'
      WHEN UPPER(P."ItemName") LIKE '%TORNILLO%'        THEN 'TORNILLOS'
      WHEN UPPER(P."ItemName") LIKE '%RESORTE%'         THEN 'RESORTES'
      WHEN UPPER(P."ItemName") LIKE '%PUERTA%'          THEN 'PUERTAS'
      ELSE 'Componente comun'
    END                                                     AS "linea_producto",
    COALESCE(NULLIF(TRIM(B."ItmsGrpNam"), ''), 'Sin grupo') AS "linea_negocio",
    COALESCE(NULLIF(TRIM(P."GRUPPE"), ''), 'Sin etapa')     AS "etapa",
    H."Material"                                            AS "material_consumido",
    H."GrupoMaterial"                                       AS "grupo_material",
    H."CodMaterial"                                         AS "codigo_material",
    -- VALIDAR CON DATOS REALES: que BELNR_ID y BELPOS_ID (y sus copias en IGE1) sean
    -- enteros.
    H."NroOT"                                               AS "nro_ot",
    H."Posicion"                                            AS "posicion",
    P."ItemCode"                                            AS "codigo_articulo",
    P."ItemName"                                            AS "nombre_articulo",
    H."Puesto"                                              AS "puesto_trabajo",
    H."Costo"                                               AS "costo"
FROM (
    -- Transformacion: tres filas por reporte, una por concepto. El CROSS JOIN contra
    -- tres constantes evita leer BEAS_ARBZEIT tres veces.
    SELECT
        CAST(Z."DocDate" AS DATE)                           AS "Fecha",
        CASE C."N" WHEN 1 THEN 'Mano de obra directa'
                   WHEN 2 THEN 'Costo variable'
                   ELSE        'Costo fijo' END             AS "Concepto",
        A."GRUPPE"                                          AS "Area",
        'Transformacion (no es material)'                   AS "Material",
        CAST(NULL AS NVARCHAR(100))                         AS "GrupoMaterial",
        CAST(NULL AS NVARCHAR(50))                          AS "CodMaterial",
        Z."BELNR_ID"                                        AS "NroOT",
        Z."BELPOS_ID"                                       AS "Posicion",
        A."BEZ"                                             AS "Puesto",
        ROUND(CASE C."N" WHEN 1 THEN Z."PCOSTVK"
                         WHEN 2 THEN Z."KOSTEN_GK"
                         ELSE        Z."KOSTEN_VK" - Z."KOSTEN_GK" END, 2) AS "Costo"
    FROM "BEAS_ARBZEIT" Z
    INNER JOIN "BEAS_APLATZ" A ON A."APLATZ_ID" = Z."APLATZ_ID"
    CROSS JOIN (
        SELECT 1 AS "N" FROM "DUMMY"
        UNION ALL SELECT 2 FROM "DUMMY"
        UNION ALL SELECT 3 FROM "DUMMY"
    ) C
    WHERE Z."CANCEL" = 0
      AND CAST(Z."DocDate" AS DATE) >= ADD_DAYS(CURRENT_DATE, -6 - DAYOFMONTH(CURRENT_DATE))
      AND CAST(Z."DocDate" AS DATE) <= CURRENT_DATE
      AND CASE C."N" WHEN 1 THEN Z."PCOSTVK"
                     WHEN 2 THEN Z."KOSTEN_GK"
                     ELSE        Z."KOSTEN_VK" - Z."KOSTEN_GK" END <> 0

    UNION ALL

    -- Material: la salida de mercancia ligada a una OT.
    SELECT
        CAST(G0."DocDate" AS DATE)                          AS "Fecha",
        CASE WHEN FB."ItemCode" IS NOT NULL THEN 'Material intermedio'
             ELSE 'Material comprado' END                   AS "Concepto",
        CASE WHEN FB."ItemCode" IS NOT NULL THEN 'Material intermedio (sin area)'
             ELSE 'Material comprado (sin area)' END        AS "Area",
        G1."Dscription"                                     AS "Material",
        -- Grupo del material CONSUMIDO, no el del articulo que se fabrica.
        COALESCE(NULLIF(TRIM(BM."ItmsGrpNam"), ''), 'Sin grupo') AS "GrupoMaterial",
        G1."ItemCode"                                       AS "CodMaterial",
        G1."U_beas_belnrid"                                 AS "NroOT",
        G1."U_beas_belposid"                                AS "Posicion",
        CAST(NULL AS NVARCHAR(100))                         AS "Puesto",
        ROUND(G1."LineTotal", 2)                            AS "Costo"
    FROM "OIGE" G0
    INNER JOIN "IGE1" G1 ON G1."DocEntry" = G0."DocEntry"
    -- Articulos que alguna vez fueron posicion de una OT: la planta los fabrica.
    LEFT JOIN (SELECT DISTINCT "ItemCode" FROM "BEAS_FTPOS") FB
           ON FB."ItemCode" = G1."ItemCode"
    LEFT JOIN "OITM" IM ON IM."ItemCode"   = G1."ItemCode"
    LEFT JOIN "OITB" BM ON BM."ItmsGrpCod" = IM."ItmsGrpCod"
    WHERE G1."U_beas_belnrid" > 0
      AND G1."LineTotal" <> 0
      AND CAST(G0."DocDate" AS DATE) >= ADD_DAYS(CURRENT_DATE, -6 - DAYOFMONTH(CURRENT_DATE))
      AND CAST(G0."DocDate" AS DATE) <= CURRENT_DATE
) H
-- La posicion de la OT: el articulo que se fabrica. INNER JOIN, como en la original.
INNER JOIN "BEAS_FTPOS" P
        ON P."BELNR_ID"  = H."NroOT"
       AND P."BELPOS_ID" = H."Posicion"
LEFT JOIN "OITM" I ON I."ItemCode"   = P."ItemCode"
LEFT JOIN "OITB" B ON B."ItmsGrpCod" = I."ItmsGrpCod"
ORDER BY H."Fecha" DESC, H."Concepto", H."Costo" DESC
