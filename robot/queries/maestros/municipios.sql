-- Municipios de la tabla de usuario del add-on HBT.
-- Conjunto MAESTROS, parte municipios (docs/contrato-robot.md §5).
-- Tabla de origen: @HBT_MUNICIPIO.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- Los alias son los nombres de columna del contrato (§5.2). Catálogo sin bandera
-- de activo: activo siempre es Y (contrato §5.1).
-- VALIDAR CON DATOS REALES: que @HBT_MUNICIPIO exista en HBT_SDERIVADOS y qué
-- columnas trae además de Code y Name (departamento, código DANE...); si trae más,
-- se propone el cambio del contrato al usuario.
SELECT
    T0."Code"                                       AS "codigo",
    T0."Name"                                       AS "nombre",
    'Y'                                             AS "activo"
FROM "@HBT_MUNICIPIO" T0
ORDER BY T0."Code"
