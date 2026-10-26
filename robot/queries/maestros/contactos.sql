-- Personas de contacto de clientes y proveedores.
-- Conjunto MAESTROS, parte contactos (docs/contrato-robot.md §5).
-- Tablas de origen: OCPR, unida a OCRD para quedarse con clientes y proveedores.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- Los alias son los nombres de columna del contrato (§5.2). El robot se queda
-- solo con los contactos de los socios que envía en la corrida (filtro por
-- codigo_socio, robot/etl/consultas.py).
-- VALIDAR CON DATOS REALES: que cambiar un contacto mueva OCRD.UpdateDate del socio;
-- si no lo mueve, una corrida de cambios no trae el contacto nuevo.
SELECT
    T0."CntctCode"                                  AS "contacto_id",
    T0."CardCode"                                   AS "codigo_socio",
    T0."Name"                                       AS "nombre",
    T0."FirstName"                                  AS "nombres",
    T0."LastName"                                   AS "apellidos",
    T0."Position"                                   AS "cargo",
    T0."Tel1"                                       AS "telefono",
    T0."Cellolar"                                   AS "celular",
    T0."E_MailL"                                    AS "correo",
    CASE WHEN T0."Active" = 'Y' THEN 'Y' ELSE 'N' END AS "activo"
FROM "OCPR" T0
INNER JOIN "OCRD" T1 ON T1."CardCode" = T0."CardCode"
WHERE T1."CardType" IN ('C', 'S')
ORDER BY T0."CntctCode"
