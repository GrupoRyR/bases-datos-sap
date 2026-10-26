<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * The stable v_* views of MAESTROS (docs/arquitectura.md, section 4). Apps
 * read only these, with a read-only MySQL user, so the tables can change
 * without breaking them. Columns are listed one by one: a new table column
 * never shows up in a view by accident, and the internal id and run never do.
 *
 * Changing a view breaks the apps: add columns at the end, never rename or
 * drop one, and do it in a new migration.
 */
return new class extends Migration
{
    protected $connection = 'maestros';

    private const BUSINESS_PARTNER = [
        'codigo', 'nombre', 'nombre_extranjero', 'nit', 'grupo_codigo', 'vendedor_codigo',
        'condicion_pago_codigo', 'lista_precios_codigo', 'telefono', 'telefono_2', 'celular', 'correo',
        'ciudad', 'limite_credito', 'socio_vinculado', 'creado_en_sap',
    ];

    private const CATALOG = ['codigo', 'nombre'];

    /** @var array<string, list<string>> The view columns of each table, between empresa and the row flags. */
    private const VIEWS = [
        'clientes' => self::BUSINESS_PARTNER,
        'proveedores' => self::BUSINESS_PARTNER,
        'direcciones' => [
            'codigo_socio', 'tipo', 'nombre', 'calle', 'barrio', 'ciudad', 'municipio_codigo',
            'departamento', 'pais', 'codigo_postal',
        ],
        'contactos' => [
            'contacto_id', 'codigo_socio', 'nombre', 'nombres', 'apellidos', 'cargo', 'telefono', 'celular', 'correo',
        ],
        'articulos' => [
            'codigo', 'nombre', 'nombre_extranjero', 'grupo_codigo', 'marca_codigo', 'unidad_venta',
            'codigo_barras', 'inventariable', 'de_venta', 'de_compra', 'creado_en_sap',
        ],
        'grupos_articulos' => self::CATALOG,
        'marcas' => self::CATALOG,
        'precios' => ['articulo_codigo', 'lista_codigo', 'lista_nombre', 'precio', 'moneda'],
        'vendedores' => ['codigo', 'nombre', 'correo', 'celular'],
        'grupos_clientes' => self::CATALOG,
        'condiciones_pago' => ['codigo', 'nombre', 'dias_extra', 'meses_extra'],
        'municipios' => self::CATALOG,
    ];

    public function up(): void
    {
        foreach (self::VIEWS as $table => $columns) {
            $select = implode(', ', ['empresa', ...$columns, 'activo', 'actualizado_en_sap', 'sincronizado_en']);

            DB::statement("CREATE VIEW v_{$table} AS SELECT {$select} FROM {$table}");
        }
    }

    public function down(): void
    {
        foreach (array_keys(self::VIEWS) as $table) {
            DB::statement("DROP VIEW IF EXISTS v_{$table}");
        }
    }
};
