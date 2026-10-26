-- Artículos de SAP Business One.
-- Conjunto MAESTROS, parte articulos (docs/contrato-robot.md §5).
-- Tabla de origen: OITM.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- Los alias son los nombres de columna del contrato (§5.2). El robot agrega
-- sus filtros por fuera (robot/etl/consultas.py) sin editar este archivo.
SELECT
    T0."ItemCode"                                   AS "codigo",
    T0."ItemName"                                   AS "nombre",
    T0."FrgnName"                                   AS "nombre_extranjero",
    T0."ItmsGrpCod"                                 AS "grupo_codigo",
    T0."FirmCode"                                   AS "marca_codigo",
    T0."SalUnitMsr"                                 AS "unidad_venta",
    T0."CodeBars"                                   AS "codigo_barras",
    T0."InvntItem"                                  AS "inventariable",
    T0."SellItem"                                   AS "de_venta",
    T0."PrchseItem"                                 AS "de_compra",
    -- VALIDAR CON DATOS REALES: que validFor = 'N' o frozenFor = 'Y' marque de verdad
    -- al artículo como inactivo (SAP B1 también usa validFrom/validTo y
    -- frozenFrom/frozenTo, que aquí no se miran).
    CASE WHEN T0."validFor" = 'N' OR T0."frozenFor" = 'Y'
         THEN 'N' ELSE 'Y' END                      AS "activo",
    -- UpdateDate + UpdateTS (entero HHMMSS) como hora local de Bogotá. Sin UpdateTS
    -- se toma 00:00:00; sin UpdateDate se usa CreateDate (contrato §5.1).
    -- VALIDAR CON DATOS REALES: que la columna UpdateTS exista en OITM y sea HHMMSS.
    ADD_SECONDS(
        CAST(IFNULL(T0."UpdateDate", T0."CreateDate") AS TIMESTAMP),
        CASE WHEN T0."UpdateDate" IS NULL OR T0."UpdateTS" IS NULL THEN 0
             ELSE FLOOR(T0."UpdateTS" / 10000) * 3600
                  + MOD(FLOOR(T0."UpdateTS" / 100), 100) * 60
                  + MOD(T0."UpdateTS", 100)
        END)                                        AS "actualizado_en_sap",
    T0."CreateDate"                                 AS "creado_en_sap"
FROM "OITM" T0
ORDER BY T0."ItemCode"
