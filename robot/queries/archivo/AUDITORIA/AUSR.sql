-- Archivo: historial de cambios de usuarios (AUSR).
-- Carpeta AUDITORIA (plan §5), registro: cada noche se suman los días nuevos por la columna UpdateDate (aaaa-mm.csv, no se borra).
-- Solo va a la carpeta BASES_SAP_CSV_DIR; nunca se envía a la API.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- VALIDAR CON DATOS REALES: columnas tomadas de la documentación de SAP B1; confirmarlas con _CATALOGO\<empresa>\columnas antes de la primera extracción.
-- Sin columnas de claves: nunca se agregan las de contraseña de AUSR.
SELECT
    T0."LogInstanc",
    T0."USERID",
    T0."USER_CODE",
    T0."U_NAME",
    T0."E_Mail",
    T0."SUPERUSER",
    T0."Locked",
    T0."UpdateDate"
FROM "AUSR" T0
ORDER BY T0."USERID", T0."LogInstanc"
