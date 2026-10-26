-- Clientes de SAP Business One (socios de negocio con CardType = 'C').
-- Conjunto MAESTROS, parte clientes (docs/contrato-robot.md §5).
-- Tabla de origen: OCRD.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- Los alias son los nombres de columna del contrato (§5.2). El robot agrega
-- sus filtros por fuera (robot/etl/consultas.py) sin editar este archivo.
SELECT
    T0."CardCode"                                   AS "codigo",
    T0."CardName"                                   AS "nombre",
    T0."CardFName"                                  AS "nombre_extranjero",
    T0."LicTradNum"                                 AS "nit",
    T0."GroupCode"                                  AS "grupo_codigo",
    IFNULL(T0."SlpCode", -1)                        AS "vendedor_codigo",
    T0."GroupNum"                                   AS "condicion_pago_codigo",
    T0."ListNum"                                    AS "lista_precios_codigo",
    T0."Phone1"                                     AS "telefono",
    T0."Phone2"                                     AS "telefono_2",
    T0."Cellular"                                   AS "celular",
    T0."E_Mail"                                     AS "correo",
    T0."City"                                       AS "ciudad",
    T0."CreditLine"                                 AS "limite_credito",
    T0."ConnBP"                                     AS "socio_vinculado",
    -- VALIDAR CON DATOS REALES: que validFor = 'N' o frozenFor = 'Y' marque de verdad
    -- al socio como inactivo (SAP B1 también usa validFrom/validTo y frozenFrom/frozenTo,
    -- que aquí no se miran).
    CASE WHEN T0."validFor" = 'N' OR T0."frozenFor" = 'Y'
         THEN 'N' ELSE 'Y' END                      AS "activo",
    -- UpdateDate + UpdateTS (entero HHMMSS) como hora local de Bogotá. Sin UpdateTS
    -- se toma 00:00:00; sin UpdateDate se usa CreateDate (contrato §5.1).
    ADD_SECONDS(
        CAST(IFNULL(T0."UpdateDate", T0."CreateDate") AS TIMESTAMP),
        CASE WHEN T0."UpdateDate" IS NULL OR T0."UpdateTS" IS NULL THEN 0
             ELSE FLOOR(T0."UpdateTS" / 10000) * 3600
                  + MOD(FLOOR(T0."UpdateTS" / 100), 100) * 60
                  + MOD(T0."UpdateTS", 100)
        END)                                        AS "actualizado_en_sap",
    T0."CreateDate"                                 AS "creado_en_sap"
FROM "OCRD" T0
WHERE T0."CardType" = 'C'
ORDER BY T0."CardCode"
