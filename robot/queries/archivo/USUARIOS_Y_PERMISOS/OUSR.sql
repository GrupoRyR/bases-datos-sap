-- Archivo: usuarios de SAP (OUSR).
-- Carpeta USUARIOS_Y_PERMISOS (plan §5), foto completa cada domingo (aaaa-mm-dd.csv, 52 semanas).
-- Solo va a la carpeta BASES_SAP_CSV_DIR; nunca se envía a la API.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- VALIDAR CON DATOS REALES: columnas tomadas de la documentación de SAP B1; confirmarlas con _CATALOGO\<empresa>\columnas antes de la primera extracción.
-- Sin columnas de claves: solo estas columnas; nunca las de contraseña de OUSR (plan §5).
-- Los permisos estándar vienen codificados en un campo que no se lee por SQL.
SELECT
    T0."USERID",
    T0."USER_CODE",
    T0."U_NAME",
    T0."E_Mail",
    T0."SUPERUSER",
    T0."Locked",
    T0."Department",
    T0."Branch"
FROM "OUSR" T0
ORDER BY T0."USERID"
