-- Archivo: cuentas bancarias propias de la empresa (DSC1).
-- Carpeta BANCOS (plan §5), foto completa cada domingo (aaaa-mm-dd.csv, 52 semanas).
-- Solo va a la carpeta BASES_SAP_CSV_DIR; nunca se envía a la API.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- VALIDAR CON DATOS REALES: columnas tomadas de la documentación de SAP B1; confirmarlas con _CATALOGO\<empresa>\columnas antes de la primera extracción.
-- Solo las cuentas propias; las de clientes y proveedores no se extraen (plan §5).
SELECT
    T0."AbsEntry",
    T0."BankCode",
    T0."Account",
    T0."Branch",
    T0."GLAccount",
    T0."AcctName",
    T0."Country"
FROM "DSC1" T0
ORDER BY T0."AbsEntry"
