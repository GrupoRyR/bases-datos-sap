-- Pedidos de clientes abiertos (SAP Business One sobre HANA), contrato §11
-- Conjunto PEDIDOS, parte "pedidos": una fila por linea abierta de un pedido
-- de cliente (ORDR/RDR1). Es una foto del estado abierto en el momento de la
-- extraccion: la API reemplaza todos los pedidos de la empresa en cada corrida.
--
-- Llave natural: "doc_entry" + "linea".
-- Los alias son los nombres del contrato, en su orden (§11.3).
--
-- Filtro (§11.2): pedido abierto y no anulado, linea abierta y con cantidad
-- pendiente. Sin filtro por bodega, lista de precios ni direccion. Solo se
-- unen OCRD, OSLP, OCRG, OITM, OITB y OMRC, con LEFT JOIN: las tablas de
-- direcciones, existencias por bodega, precios por lista y las direcciones
-- del documento multiplican o pierden lineas y no se unen.
--
-- Cantidades en unidades de venta (las del precio): "cantidad_pendiente" es
-- OpenCreQty. OpenInvQty va en unidades de inventario y no sirve para valorar
-- (en el pedido 3859 de SDC daba 10.000 contra 400, NumInSale 25).
--
-- Valores pendientes en pesos, proporcionales a la cantidad abierta:
--   total_pendiente = LineTotal * OpenCreQty / Quantity * (1 - descuento del documento)
--   ganancia_bruta_pendiente = GrssProfit * OpenCreQty / Quantity
-- Las lineas "Solo impuesto" (TaxOnly = 'Y') y las de cantidad 0 van en 0.
-- El NULLIF protege la division aunque HANA evaluara la rama del ELSE.
-- Precios unitarios en la moneda de la linea; el robot los deja con 2 decimales.
--
-- Dias contados con CURRENT_DATE del servidor HANA:
--   "dias"        = desde la fecha del pedido;
--   "dias_atraso" = desde la fecha de compromiso: negativo si aun no vence.
-- Valores de "rango" (texto ASCII exacto): Hasta 30 dias | De 31 a 60 dias |
-- De 61 a 90 dias | Mas de 90 dias.
--
-- Dos expresiones solo existen en SEGUREX y llevan su marca al final de la
-- linea; para Derivados el robot las cambia por un NULL del mismo tipo
-- (robot/etl/consultas.py). Si se corre a mano en Derivados, cambiarlas igual.
SELECT
    T0."DocEntry"                                              AS "doc_entry",
    T0."DocNum"                                                AS "numero_pedido",
    T1."LineNum"                                               AS "linea",
    T0."DocDate"                                               AS "fecha_pedido",
    T0."DocDueDate"                                            AS "fecha_compromiso",
    T1."ShipDate"                                              AS "fecha_entrega_linea",
    DAYS_BETWEEN(T0."DocDate", CURRENT_DATE)                   AS "dias",
    CASE
        WHEN DAYS_BETWEEN(T0."DocDate", CURRENT_DATE) <= 30 THEN 'Hasta 30 dias'
        WHEN DAYS_BETWEEN(T0."DocDate", CURRENT_DATE) <= 60 THEN 'De 31 a 60 dias'
        WHEN DAYS_BETWEEN(T0."DocDate", CURRENT_DATE) <= 90 THEN 'De 61 a 90 dias'
        ELSE 'Mas de 90 dias'
    END                                                        AS "rango",
    DAYS_BETWEEN(T0."DocDueDate", CURRENT_DATE)                AS "dias_atraso",
    IFNULL(T0."SlpCode", -1)                                   AS "slp_code",
    T3."SlpName"                                               AS "vendedor",
    -- Canal = grupo del cliente (OCRG): la «unidad de negocio» del panel.
    T7."GroupName"                                             AS "canal",
    T0."CardCode"                                              AS "codigo_cliente",
    T0."CardName"                                              AS "cliente",
    T2."LicTradNum"                                            AS "nit",
    T2."City"                                                  AS "ciudad",
    -- Id del pedido de la app de ventas (ORDR.U_SGX_IdPedidoApp), solo SEGUREX.
    -- VALIDAR CON DATOS REALES: que U_SGX_IdPedidoApp exista en ORDR de SEGUREX;
    -- si no, HANA responde "invalid column name" y falla toda la corrida.
    CAST(T0."U_SGX_IdPedidoApp" AS NVARCHAR(254))              AS "id_pedido_app", -- @id_pedido_app
    T0."NumAtCard"                                             AS "oc_cliente",
    T0."Address2"                                              AS "direccion_envio",
    T0."Comments"                                              AS "comentarios",
    T1."ItemCode"                                              AS "codigo_articulo",
    T1."Dscription"                                            AS "descripcion",
    -- Grupo de articulos (OITB): la «Linea» del panel. En VENTAS este dato se
    -- llama "familia"; aqui "familia" es el campo de usuario de abajo.
    T5."ItmsGrpNam"                                            AS "linea_articulo",
    -- Familia del articulo (OITM.U_GSP_FAMILIA), solo SEGUREX.
    -- VALIDAR CON DATOS REALES: que U_GSP_FAMILIA exista en OITM de SEGUREX.
    CAST(T4."U_GSP_FAMILIA" AS NVARCHAR(100))                  AS "familia", -- @familia
    T6."FirmName"                                              AS "marca",
    T1."WhsCode"                                               AS "bodega",
    -- VALIDAR CON DATOS REALES: que unitMsr venga lleno en las dos empresas.
    T1."unitMsr"                                               AS "unidad",
    T1."Quantity"                                              AS "cantidad_pedida",
    T1."OpenCreQty"                                            AS "cantidad_pendiente",
    T1."PriceBefDi"                                            AS "precio_lista",
    T1."Price"                                                 AS "precio_unitario",
    T0."DiscPrcnt"                                             AS "descuento_documento",
    -- VALIDAR CON DATOS REALES: que LineTotal y GrssProfit de RDR1 vengan en
    -- pesos en un pedido en otra moneda (revisarlo contra el informe de SAP).
    CASE WHEN T1."TaxOnly" = 'Y' OR IFNULL(T1."Quantity", 0) = 0 THEN 0
         ELSE ROUND(T1."LineTotal" * T1."OpenCreQty" / NULLIF(T1."Quantity", 0)
                    * (1 - IFNULL(T0."DiscPrcnt", 0) / 100), 2)
    END                                                        AS "total_pendiente",
    CASE WHEN T1."TaxOnly" = 'Y' OR IFNULL(T1."Quantity", 0) = 0 THEN 0
         ELSE ROUND(T1."GrssProfit" * T1."OpenCreQty" / NULLIF(T1."Quantity", 0), 2)
    END                                                        AS "ganancia_bruta_pendiente",
    T0."DocCur"                                                AS "moneda",
    T0."DocRate"                                               AS "trm"
FROM "ORDR" T0
INNER JOIN "RDR1" T1 ON T1."DocEntry" = T0."DocEntry"
LEFT JOIN "OCRD" T2 ON T2."CardCode"   = T0."CardCode"
LEFT JOIN "OSLP" T3 ON T3."SlpCode"    = T0."SlpCode"
LEFT JOIN "OITM" T4 ON T4."ItemCode"   = T1."ItemCode"
LEFT JOIN "OITB" T5 ON T5."ItmsGrpCod" = T4."ItmsGrpCod"
LEFT JOIN "OMRC" T6 ON T6."FirmCode"   = T4."FirmCode"
LEFT JOIN "OCRG" T7 ON T7."GroupCode"  = T2."GroupCode"
WHERE T0."DocStatus" = 'O'
  AND T0."CANCELED" = 'N'
  AND T1."LineStatus" = 'O'
  AND T1."OpenCreQty" > 0
ORDER BY T0."DocEntry", T1."LineNum"
