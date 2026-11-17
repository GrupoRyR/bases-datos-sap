-- Archivo: historial de cambios de usuarios (AUSR).
-- Carpeta AUDITORIA (plan §5), registro: cada noche se suman los días nuevos por la columna updateDate (aaaa-mm.csv, no se borra).
-- Solo va a la carpeta BASES_SAP_CSV_DIR; nunca se envía a la API.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- Columnas confirmadas con _CATALOGO\SEGUREX\columnas el 17/11/2026. HANA distingue
-- mayúsculas: son "logInstanc" y "updateDate", con la inicial en minúscula.
-- VALIDAR CON DATOS REALES: Derivados (HBT_SDERIVADOS) todavía no se confirmó con su
-- catálogo; corre --archivo registros y revisa el log.
-- Sin columnas de claves: nunca se agregan las de contraseña, llave o hash de AUSR.
SELECT
    T0."logInstanc",
    T0."USERID",
    T0."USER_CODE",
    T0."U_NAME",
    T0."E_Mail",
    T0."SUPERUSER",
    T0."Locked",
    T0."updateDate"
FROM "AUSR" T0
ORDER BY T0."USERID", T0."logInstanc"
