# Robot de Bases de datos SAP

Saca los datos maestros y la cartera de SAP Business One (Segurex y Soluciones y Derivados) por la VPN Sophos, guarda un respaldo en CSV y los envía a la app. El contrato con la app está en `docs/contrato-robot.md`.

Corre en el PC de TI con Windows y Python 3.14.

## Instalación

Desde la carpeta `robot/`:

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Configuración

1. Copia `.env.example` como `.env` en esta misma carpeta.
2. Llena las credenciales de la VPN, de HANA (un usuario por empresa), de la API y, si quieres alertas, del correo.

El `.env` nunca se sube a Git. Los CSV quedan en `BASES_SAP_CSV_DIR`, fuera del repo.

## Pruebas

Las pruebas usan simulaciones: no se conectan a SAP, a la VPN, a la app ni al correo.

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest
```

## Modos

Los modos de ejecución llegan en los próximos PR.
