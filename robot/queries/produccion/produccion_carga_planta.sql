-- Carga de planta: reportes de produccion de BEAS (Segurex), contrato §12
-- Conjunto PRODUCCION, parte "produccion_carga_planta". Solo SEGUREX.
-- Copia de CARGA_PLANTA_SGX.sql del tablero "Produccion mes a mes"
-- (OneDrive\Claude\automatizacion-hana\tablero-produccion-sgx\consultas), con los
-- cambios del §12 y nada mas: la ventana de VENTAS en vez del BETWEEN fijo, los
-- nombres del contrato y sin la columna de quien reporto (dato de una persona que
-- el tablero no usa).
--
-- Una fila por REPORTE DE PRODUCCION: lo que un puesto de trabajo confirmo como
-- terminado un dia, sobre una operacion de una orden de trabajo. Segurex fabrica con
-- BEAS, no con OWOR/WOR1:
--   BEAS_ARBZEIT  reporte de produccion   fecha, puesto, unidades, tiempo
--   BEAS_FTPOS    posicion de la OT       articulo que se fabrica, almacen
--   BEAS_APLATZ   puesto de trabajo       su GRUPPE es el AREA
--
-- Sin llave: dos reportes iguales del mismo dia son legitimos.
--
-- Se excluyen los anulados (CANCEL = 1): BEAS los deja con la cantidad intacta en
-- vez de revertirlos. Sumar todas las areas da unidades PROCESADAS, no piezas
-- distintas: una pieza pasa por varias areas y cada paso es un reporte.
--
-- "linea_producto" es la regla de dos pasos del tablero, copiada tal cual:
--   1. si U_GSP_FAMILIA ya es una linea (no una etapa), se usa tal cual;
--   2. si no, se reconoce la linea en el nombre del articulo.
-- Lo que no cae en ninguna (y una linea nueva de la planta, hasta que se agregue
-- aqui) queda como 'Componente comun'.
--
-- Ventana sin parametros (corre igual en el Query Manager): el mes en curso mas
-- los ultimos 7 dias del mes anterior, hasta hoy, por la fecha del reporte.
-- Es la misma expresion de VENTAS y el robot la calcula en HANA como ventana_desde.
SELECT
    CAST(Z."DocDate" AS DATE)                               AS "fecha",
    -- VALIDAR CON DATOS REALES: que BEAS_APLATZ.GRUPPE venga siempre lleno. "area" es
    -- obligatoria: una sola fila sin area hace fallar toda la corrida de PRODUCCION.
    A."GRUPPE"                                              AS "area",
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
    A."BEZ"                                                 AS "puesto_trabajo",
    -- VALIDAR CON DATOS REALES: que BELNR_ID, BELPOS_ID y POS_ID sean enteros.
    Z."BELNR_ID"                                            AS "nro_ot",
    Z."BELPOS_ID"                                           AS "posicion",
    Z."POS_ID"                                              AS "operacion",
    P."ItemCode"                                            AS "codigo_articulo",
    P."ItemName"                                            AS "nombre_articulo",
    P."ME_VERBRAUCH"                                        AS "unidad",
    Z."MENGE_GUT"                                           AS "unidades",
    Z."MENGE_SCHLECHT"                                      AS "unidades_no_conformes",
    -- ZEIT viene en minutos.
    -- VALIDAR CON DATOS REALES: el tipo de ZEIT. Si es entero, HANA podria truncar la
    -- division (90 minutos -> 1 hora); comparar las horas contra el tablero.
    Z."ZEIT" / 60                                           AS "horas",
    P."WhsCode"                                             AS "almacen",
    -- J/N = ja/nein. BEAS no usa P/R/L/C como SAP estandar.
    P."ABGKZ"                                               AS "estado_ot"
FROM "BEAS_ARBZEIT" Z
INNER JOIN "BEAS_APLATZ" A
        ON A."APLATZ_ID" = Z."APLATZ_ID"
INNER JOIN "BEAS_FTPOS" P
        ON P."BELNR_ID"  = Z."BELNR_ID"
       AND P."BELPOS_ID" = Z."BELPOS_ID"
LEFT JOIN "OITM" I
       ON I."ItemCode" = P."ItemCode"
LEFT JOIN "OITB" B
       ON B."ItmsGrpCod" = I."ItmsGrpCod"
WHERE Z."CANCEL" = 0
  AND CAST(Z."DocDate" AS DATE) >= ADD_DAYS(CURRENT_DATE, -6 - DAYOFMONTH(CURRENT_DATE))
  AND CAST(Z."DocDate" AS DATE) <= CURRENT_DATE
ORDER BY CAST(Z."DocDate" AS DATE) DESC, A."GRUPPE", Z."BELNR_ID", Z."BELPOS_ID", Z."POS_ID"
