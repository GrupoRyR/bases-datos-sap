-- Diagnóstico: listas de precios de la empresa, para confirmar el nombre exacto
-- de la lista PÚBLICA que usan maestros/<ESQUEMA>/precios.sql.
-- Va a la carpeta _DIAGNOSTICO (robot --diagnostico); nunca se envía a la API.
-- Tabla de origen: OPLN.
-- Corre tal cual en el Query Manager de SAP B1, en SEGUREX y en HBT_SDERIVADOS:
-- sin parámetros y con nombres de tabla sin esquema (lo pone la conexión).
-- VALIDAR CON DATOS REALES: los nombres de columna de OPLN (tomados de la
-- documentación de SAP B1), sobre todo BASE_NUM, Factor y ValidFor.
SELECT
    T0."ListNum",
    T0."ListName",
    T0."BASE_NUM",
    T0."Factor",
    T0."ValidFor"
FROM "OPLN" T0
ORDER BY T0."ListNum"
