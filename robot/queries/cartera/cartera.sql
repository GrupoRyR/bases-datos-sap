-- ============================================================================
-- COPIA del gestor de cartera: GESTOR_CARTERA/etl/queries/cartera.sql
-- Conjunto CARTERA, parte cartera (docs/contrato-robot.md §6). Las etiquetas
-- ("Código SN"...) se traducen a las columnas del contrato en robot/etl/esquema.py.
-- NO se edita aquí: si cambia el gestor, se copia de nuevo, completa, debajo de
-- este bloque y se quita su filtro de cuentas (ver abajo). Corre tal cual en el
-- Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS (sin parámetros; el
-- esquema lo pone la conexión).
-- Trae las cuentas por cobrar de todos los clientes, sin filtrar por cuenta: las
-- cuentas de cartera cambian por empresa y el robot se queda con las de cada una
-- por la etiqueta "Cuenta visible" (HANA_SGX_CUENTAS_CARTERA y
-- HANA_SDC_CUENTAS_CARTERA; consultas.sql_cuentas). Segurex: 13050505 y 13051005;
-- Derivados: 13050501 y 13051005. Para verla a mano como la ve el robot, agrega
-- AND T0."Account" IN (...) al WHERE de la consulta interna.
-- VALIDAR CON DATOS REALES: que las cuentas de Derivados den las mismas cifras que
-- el informe de cartera de SAP; robot --diagnostico guarda el conteo y las filas.
-- ============================================================================
-- Consulta de cartera SEGUREX (SAP Business One sobre HANA)
-- Base: consulta original entregada por el negocio.
-- ADICIONES para el sistema de permisos de la web (no alteran los importes):
--   * X."SlpCode"       -> codigo del asesor (OSLP), llave para filtrar la cartera por asesor
--   * X."Email asesor"  -> correo del asesor (OSLP), usado para el login
--
-- ADICION de valor antes de impuestos:
--   El importe de cartera es el DocTotal de la factura, IVA INCLUIDO. Para
--   mostrar tambien el valor antes de impuestos se trae el IVA real del
--   documento fiscal (OINV / ORIN) en vez de dividir por 1,19: las tarifas
--   conviven (19%, 5%, excluido) y la estimacion daria cifras falsas.
--   El cruce es por "TransId" (el asiento contable que genero la factura) y
--   cubre el 100% de facturas y notas credito. Los recibos de caja y asientos
--   manuales no tienen documento fiscal: ahi base = importe, no hay impuesto
--   que separar.
SELECT
    X."SlpCode",
    X."Email asesor",
    X."Código SN",
    X."Nombre SN",
    X."Nit",
    X."Grupo",
    X."Municipio",
    X."Cuenta visible",
    X."Tipo doc",
    X."Documento",
    X."Documento base",
    X."Referencia 1",
    X."No. referencia",
    X."Empleado ventas / compras",
    X."Total plazos",
    X."No. plazo",
    X."Condicion pago documento",
    X."Fecha contabilización",
    X."Fecha vencimiento",
    X."Fecha documento",
    X."Días",
    X."Límite crédito",
    X."Importe original",
    X."Base gravable",
    X."Saldo base",
    X."Saldo"                                                                AS "Saldo vencido",
    X."Valor abonado",
    CASE WHEN X."Días" <  0 THEN X."Saldo" ELSE 0 END                        AS "Sin vencer",
    CAST(0 AS DECIMAL(19,2))                                                 AS "Valor cheques aplicados",
    CASE WHEN X."Días" BETWEEN   0 AND  30 THEN X."Saldo" ELSE 0 END         AS "0-30",
    CASE WHEN X."Días" BETWEEN  31 AND  60 THEN X."Saldo" ELSE 0 END         AS "31-60",
    CASE WHEN X."Días" BETWEEN  61 AND  90 THEN X."Saldo" ELSE 0 END         AS "61-90",
    CASE WHEN X."Días" BETWEEN  91 AND 120 THEN X."Saldo" ELSE 0 END         AS "91-120",
    CASE WHEN X."Días" BETWEEN 121 AND 150 THEN X."Saldo" ELSE 0 END         AS "121-150",
    CASE WHEN X."Días" BETWEEN 151 AND 180 THEN X."Saldo" ELSE 0 END         AS "151-180",
    CASE WHEN X."Días" > 180 THEN X."Saldo" ELSE 0 END                       AS "> 180",
    X."Saldo"                                                                AS "Saldo",
    CASE
        WHEN X."Días" <   0 THEN 'Sin vencer'
        WHEN X."Días" <=  30 THEN '0-30'
        WHEN X."Días" <=  60 THEN '31-60'
        WHEN X."Días" <=  90 THEN '61-90'
        WHEN X."Días" <= 120 THEN '91-120'
        WHEN X."Días" <= 150 THEN '121-150'
        WHEN X."Días" <= 180 THEN '151-180'
        ELSE '> 180'
    END                                                                      AS "Rango"
FROM (
    SELECT
        IFNULL(T1."SlpCode", -1)                          AS "SlpCode",
        LOWER(IFNULL(T3."Email", ''))                     AS "Email asesor",
        T1."CardCode"                                     AS "Código SN",
        T1."CardName"                                     AS "Nombre SN",
        T1."LicTradNum"                                   AS "Nit",
        IFNULL(T2."GroupName", '')                        AS "Grupo",
        IFNULL(T1."City", '')                             AS "Municipio",
        T0."Account"                                      AS "Cuenta visible",
        T0."TransType"                                    AS "Tipo doc",
        T0."BaseRef"                                      AS "Documento",
        T0."Ref1"                                         AS "Documento base",
        T0."Ref1"                                         AS "Referencia 1",
        T0."Ref2"                                         AS "No. referencia",
        IFNULL(T3."SlpName", '')                          AS "Empleado ventas / compras",
        CAST(0 AS INTEGER)                                AS "Total plazos",
        T0."Line_ID"                                      AS "No. plazo",
        IFNULL(T4."PymntGroup", '')                       AS "Condicion pago documento",
        T0."RefDate"                                      AS "Fecha contabilización",
        T0."DueDate"                                      AS "Fecha vencimiento",
        T0."TaxDate"                                      AS "Fecha documento",
        DAYS_BETWEEN(T0."DueDate", CURRENT_DATE)          AS "Días",
        T1."CreditLine"                                   AS "Límite crédito",
        (T0."Debit" - T0."Credit")                        AS "Importe original",
        CASE WHEN IFNULL(T5."DocTotal", 0) <> 0
             THEN ROUND((T0."Debit" - T0."Credit")
                        * (1 - T5."VatSum" / T5."DocTotal"), 2)
             ELSE (T0."Debit" - T0."Credit")
        END                                               AS "Base gravable",
        CASE WHEN IFNULL(T5."DocTotal", 0) <> 0
             THEN ROUND((T0."BalDueDeb" - T0."BalDueCred")
                        * (1 - T5."VatSum" / T5."DocTotal"), 2)
             ELSE (T0."BalDueDeb" - T0."BalDueCred")
        END                                               AS "Saldo base",
        CAST(0 AS DECIMAL(19,2))                          AS "Valor abonado",
        (T0."BalDueDeb" - T0."BalDueCred")                AS "Saldo"
    FROM "JDT1" T0
    INNER JOIN "OCRD" T1 ON T0."ShortName"  = T1."CardCode"
    LEFT  JOIN "OCRG" T2 ON T1."GroupCode"  = T2."GroupCode"
    LEFT  JOIN "OSLP" T3 ON T1."SlpCode"    = T3."SlpCode"
    LEFT  JOIN "OCTG" T4 ON T1."GroupNum"   = T4."GroupNum"
    -- Documento fiscal del asiento: factura (OINV) o nota credito (ORIN).
    LEFT  JOIN (
        SELECT "TransId", "DocTotal", "VatSum" FROM "OINV"
        UNION ALL
        SELECT "TransId", "DocTotal", "VatSum" FROM "ORIN"
    ) T5 ON T0."TransId" = T5."TransId"
    WHERE T1."CardType" = 'C'
      AND (T0."BalDueDeb" - T0."BalDueCred") <> 0
) X
ORDER BY X."Nombre SN", X."Fecha vencimiento"
