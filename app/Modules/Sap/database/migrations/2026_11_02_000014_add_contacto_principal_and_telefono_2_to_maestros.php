<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Adds contacto_principal (OCRD.CntctPrsn, the name of the main contact) to
 * clientes and proveedores, and telefono_2 (OCPR.Tel2) to contactos
 * (docs/contrato-robot.md, section 5.2), and recreates their views with the
 * new column at the end, after sincronizado_en: a view only grows at the
 * end, so the apps that list their columns keep working. Both columns are
 * nullable: the batches that arrive before the robot sends them, and the
 * rows already stored, carry null.
 */
return new class extends Migration
{
    protected $connection = 'maestros';

    private const BUSINESS_PARTNER = [
        'codigo', 'nombre', 'nombre_extranjero', 'nit', 'grupo_codigo', 'vendedor_codigo',
        'condicion_pago_codigo', 'lista_precios_codigo', 'telefono', 'telefono_2', 'celular', 'correo',
        'ciudad', 'limite_credito', 'socio_vinculado', 'creado_en_sap',
    ];

    /** @var array<string, array{0: list<string>, 1: string, 2: int}> Each table: its view columns before the row flags, the new column and its length. */
    private const TABLES = [
        'clientes' => [self::BUSINESS_PARTNER, 'contacto_principal', 255],
        'proveedores' => [self::BUSINESS_PARTNER, 'contacto_principal', 255],
        'contactos' => [
            ['contacto_id', 'codigo_socio', 'nombre', 'nombres', 'apellidos', 'cargo', 'telefono', 'celular', 'correo'],
            'telefono_2',
            50,
        ],
    ];

    public function up(): void
    {
        DB::connection()->reconnectIfMissingConnection();

        foreach (self::TABLES as $table => [$columns, $new, $length]) {
            Schema::table($table, function (Blueprint $blueprint) use ($new, $length) {
                $blueprint->string($new, $length)->nullable();
            });

            $this->recreateView($table, [...$columns, 'activo', 'actualizado_en_sap', 'sincronizado_en', $new]);
        }
    }

    public function down(): void
    {
        DB::connection()->reconnectIfMissingConnection();

        foreach (self::TABLES as $table => [$columns, $new]) {
            $this->recreateView($table, [...$columns, 'activo', 'actualizado_en_sap', 'sincronizado_en']);

            Schema::table($table, function (Blueprint $blueprint) use ($new) {
                $blueprint->dropColumn($new);
            });
        }
    }

    /**
     * @param  list<string>  $columns
     */
    private function recreateView(string $table, array $columns): void
    {
        $list = implode(', ', ['empresa', ...$columns]);

        DB::statement("DROP VIEW IF EXISTS v_{$table}");
        DB::statement("CREATE VIEW v_{$table} AS SELECT {$list} FROM {$table}");
    }
};
