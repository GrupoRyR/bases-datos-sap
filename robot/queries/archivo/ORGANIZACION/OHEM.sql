-- Archivo: empleados (OHEM).
-- Carpeta ORGANIZACION (plan §5), foto completa cada domingo (aaaa-mm-dd.csv, 52 semanas).
-- Solo va a la carpeta BASES_SAP_CSV_DIR; nunca se envía a la API.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- VALIDAR CON DATOS REALES: columnas tomadas de la documentación de SAP B1; confirmarlas con _CATALOGO\<empresa>\columnas antes de la primera extracción.
-- Solo nombre, cargo, área y correo (plan §5): nunca cédula, salario ni cuentas
-- bancarias del empleado.
SELECT
    T0."empID",
    T0."firstName",
    T0."middleName",
    T0."lastName",
    T0."jobTitle",
    T0."position",
    T0."dept",
    T0."email"
FROM "OHEM" T0
ORDER BY T0."empID"
