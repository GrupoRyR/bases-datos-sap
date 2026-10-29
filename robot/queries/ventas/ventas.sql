-- Ventas detalladas SEGUREX (SAP Business One sobre HANA)
-- Lote "ventas" del gestor de cartera (Comisiones, Parte B reporte 1): base de
-- la comision por venta y del cumplimiento de presupuesto.
--
-- Una fila por linea de:
--   * factura de clientes (OINV/INV1, objeto 13); "DocSubType" = 'DN' es una
--     nota debito, que en B1 tambien es una factura de clientes;
--   * nota credito de clientes (ORIN/RIN1, objeto 14), con signo NEGATIVO en
--     cantidad, costo total, total e IVA: la suma de "Total" es la venta neta.
-- Se incluyen los documentos anulados (CANCELED = 'Y') y los documentos de
-- anulacion (CANCELED = 'C') con su estado: un original y su anulacion suman
-- cero y Comisiones los puede excluir o netear.
--
-- Llave natural: "Tipo objeto" + "DocEntry" + "Línea".
--
-- Periodo: la venta se asigna al mes de la fecha de la factura (DocDate, la
-- de la factura electronica), que sale en "Fecha contabilización". "Fecha
-- documento" (TaxDate) se conserva solo como referencia.
--
-- Ventana sin parametros (para que corra igual en el Query Manager): el mes en
-- curso mas los ultimos 7 dias del mes anterior, hasta hoy, por la fecha de la
-- factura (DocDate).
--   ADD_DAYS(CURRENT_DATE, -6 - DAYOFMONTH(CURRENT_DATE))
--     = CURRENT_DATE - (DAYOFMONTH - 1)   -> primer dia del mes en curso
--                    - 7                  -> menos 7 dias
--   Ej: el 16/10 resta 22 dias -> 24/09; el 01/10 resta 7 dias -> 24/09.
--   CURRENT_DATE es la fecha del servidor HANA.
--
-- Montos en moneda local (COP). "Total" (base de comision) = LineTotal (antes
-- de IVA, ya con el descuento de la linea) menos el descuento global del
-- documento (DiscPrcnt), redondeado a 2 decimales y con signo.
-- Las lineas "Solo impuesto" (TaxOnly = 'Y' en INV1/RIN1) solo cobran el IVA y
-- SAP no las cuenta como venta: su "Total", "Costo unitario" y "Costo total"
-- son 0 (ganancia bruta 0, como en el Analisis de ventas de SAP). La linea se
-- conserva, con su cantidad y su IVA.
-- Precios y costos unitarios van sin signo; solo los totales llevan signo.
--
-- Valores de texto:
--   "Clase documento":  factura | nota_debito | nota_credito
--   "Estado documento": anulado | anulacion | cerrado | abierto
SELECT
    X."ObjType"                                                AS "Tipo objeto",
    X."DocEntry"                                               AS "DocEntry",
    X."DocNum"                                                 AS "Número documento",
    X."LineNum"                                                AS "Línea",
    CASE
        WHEN X."ObjType" = 14 THEN 'nota_credito'
        WHEN X."DocSubType" = 'DN' THEN 'nota_debito'
        ELSE 'factura'
    END                                                        AS "Clase documento",
    CASE
        WHEN X."CANCELED" = 'Y' THEN 'anulado'
        WHEN X."CANCELED" = 'C' THEN 'anulacion'
        WHEN X."DocStatus" = 'C' THEN 'cerrado'
        ELSE 'abierto'
    END                                                        AS "Estado documento",
    -- El periodo va por DocDate ("Fecha contabilización"), confirmado por
    -- Miguel. TaxDate se envia como referencia.
    X."TaxDate"                                                AS "Fecha documento",
    X."DocDate"                                                AS "Fecha contabilización",
    IFNULL(X."SlpCode", -1)                                    AS "SlpCode",
    T3."SlpName"                                               AS "Vendedor",
    -- Canal = grupo del cliente de la factura (OCRG), confirmado por Miguel.
    T7."GroupName"                                             AS "Canal",
    X."CardCode"                                               AS "Código cliente",
    X."CardName"                                               AS "Cliente",
    T2."LicTradNum"                                            AS "Nit",
    T2."City"                                                  AS "Ciudad",
    -- VALIDAR CON DATOS REALES: pedido = documento base de la linea cuando es
    -- un pedido de cliente (BaseType 17; BaseRef es el DocNum del pedido). Si
    -- la factura sale de una entrega (BaseType 15), el pedido queda un paso
    -- atras y aqui sale NULL.
    CASE WHEN X."BaseType" = 17 THEN X."BaseRef" END           AS "Pedido",
    -- Id del pedido de la app de ventas: campo de usuario de la factura
    -- (OINV."U_SGX_IdPedidoApp"), confirmado por Miguel. Las notas credito lo
    -- traen en NULL. El campo solo existe en SEGUREX: para Derivados el robot
    -- reemplaza la expresion marcada al final de la linea por un NULL (config.py).
    -- VALIDAR CON DATOS REALES: si el campo tiene otro nombre en SEGUREX, HANA
    -- responde "invalid column name" y falla todo el lote de ventas.
    X."IdPedidoApp"                                            AS "Id pedido app",
    X."NumAtCard"                                              AS "OC cliente",
    -- VALIDAR CON DATOS REALES: la ciudad de envio no esta separada en el
    -- encabezado (Address2 es la direccion completa). Candidata: INV12/RIN12
    -- columna "CityS". Va en NULL hasta confirmarla.
    CAST(NULL AS NVARCHAR(100))                                AS "Ciudad envío",
    X."Address2"                                               AS "Dirección envío",
    T6."FirmName"                                              AS "Marca",
    T5."ItmsGrpNam"                                            AS "Familia",
    X."ItemCode"                                               AS "Código artículo",
    X."Dscription"                                             AS "Descripción",
    IFNULL(X."Quantity", 0) * X."Signo"                        AS "Cantidad",
    -- VALIDAR CON DATOS REALES: costo = StockPrice de la linea (costo de
    -- inventario al contabilizar). Confirmar contra el margen del informe
    -- actual; en lineas de servicio puede venir en 0 o NULL.
    CASE WHEN X."TaxOnly" = 'Y' THEN 0
         ELSE ROUND(X."StockPrice", 2)
    END                                                        AS "Costo unitario",
    CASE WHEN X."TaxOnly" = 'Y' THEN 0
         ELSE ROUND(X."StockPrice" * X."Quantity", 2) * X."Signo"
    END                                                        AS "Costo total",
    -- VALIDAR CON DATOS REALES: precio lista = precio antes del descuento de
    -- la linea (PriceBefDi), no el de la lista de precios del articulo (ITM1).
    ROUND(X."PriceBefDi", 2)                                   AS "Precio lista",
    ROUND(X."Price", 2)                                        AS "Precio unitario",
    CASE WHEN X."TaxOnly" = 'Y' THEN 0
         ELSE ROUND(IFNULL(X."LineTotal", 0)
                    * (1 - IFNULL(X."DiscPrcnt", 0) / 100), 2) * X."Signo"
    END                                                        AS "Total",
    ROUND(X."VatSum", 2) * X."Signo"                           AS "IVA",
    X."DocCur"                                                 AS "Moneda",
    X."DocRate"                                                AS "TRM",
    X."Comments"                                               AS "Comentarios"
FROM (
    -- Facturas y notas debito: signo positivo.
    SELECT
        13 AS "ObjType", 1 AS "Signo",
        T0."DocEntry", T0."DocNum", T0."DocSubType", T0."CANCELED", T0."DocStatus",
        T0."DocDate", T0."TaxDate", T0."SlpCode", T0."CardCode", T0."CardName",
        T0."NumAtCard", T0."Address2", T0."DiscPrcnt", T0."DocCur", T0."DocRate",
        T0."Comments",
        T1."LineNum", T1."ItemCode", T1."Dscription", T1."Quantity", T1."Price",
        T1."PriceBefDi", T1."StockPrice", T1."LineTotal", T1."VatSum",
        T1."TaxOnly", T1."BaseType", T1."BaseRef",
        CAST(T0."U_SGX_IdPedidoApp" AS NVARCHAR(254)) AS "IdPedidoApp" -- @id_pedido_app
    FROM "OINV" T0
    INNER JOIN "INV1" T1 ON T1."DocEntry" = T0."DocEntry"
    WHERE T0."DocDate" >= ADD_DAYS(CURRENT_DATE, -6 - DAYOFMONTH(CURRENT_DATE))
      AND T0."DocDate" <= CURRENT_DATE

    UNION ALL

    -- Notas credito: signo negativo.
    SELECT
        14 AS "ObjType", -1 AS "Signo",
        T0."DocEntry", T0."DocNum", T0."DocSubType", T0."CANCELED", T0."DocStatus",
        T0."DocDate", T0."TaxDate", T0."SlpCode", T0."CardCode", T0."CardName",
        T0."NumAtCard", T0."Address2", T0."DiscPrcnt", T0."DocCur", T0."DocRate",
        T0."Comments",
        T1."LineNum", T1."ItemCode", T1."Dscription", T1."Quantity", T1."Price",
        T1."PriceBefDi", T1."StockPrice", T1."LineTotal", T1."VatSum",
        T1."TaxOnly", T1."BaseType", T1."BaseRef",
        CAST(NULL AS NVARCHAR(254)) AS "IdPedidoApp"
    FROM "ORIN" T0
    INNER JOIN "RIN1" T1 ON T1."DocEntry" = T0."DocEntry"
    WHERE T0."DocDate" >= ADD_DAYS(CURRENT_DATE, -6 - DAYOFMONTH(CURRENT_DATE))
      AND T0."DocDate" <= CURRENT_DATE
) X
LEFT JOIN "OCRD" T2 ON T2."CardCode"   = X."CardCode"
LEFT JOIN "OSLP" T3 ON T3."SlpCode"    = X."SlpCode"
LEFT JOIN "OITM" T4 ON T4."ItemCode"   = X."ItemCode"
LEFT JOIN "OITB" T5 ON T5."ItmsGrpCod" = T4."ItmsGrpCod"
LEFT JOIN "OMRC" T6 ON T6."FirmCode"   = T4."FirmCode"
LEFT JOIN "OCRG" T7 ON T7."GroupCode"  = T2."GroupCode"
ORDER BY X."DocDate", X."ObjType", X."DocEntry", X."LineNum"
