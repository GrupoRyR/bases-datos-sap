-- Empleados de ventas (asesores) de SAP Business One, sin el "-1 Ningún empleado".
-- Conjunto MAESTROS, parte vendedores (docs/contrato-robot.md §5).
-- Tabla de origen: OSLP.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- Los alias son los nombres de columna del contrato (§5.2).
SELECT
    T0."SlpCode"                                    AS "codigo",
    T0."SlpName"                                    AS "nombre",
    T0."Email"                                      AS "correo",
    T0."Mobil"                                      AS "celular",
    CASE WHEN T0."Active" = 'Y' THEN 'Y' ELSE 'N' END AS "activo"
FROM "OSLP" T0
WHERE T0."SlpCode" >= 0
ORDER BY T0."SlpCode"
