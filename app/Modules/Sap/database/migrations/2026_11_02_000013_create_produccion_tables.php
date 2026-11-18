<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * PRODUCCION in ventas_sap, next to VENTAS and PEDIDOS (docs/contrato-robot.md,
 * section 12). Segurex only, but every row still carries its company.
 *
 * - Movement, replaced from the run's ventana_desde on by fecha:
 *   produccion_terminado (unique by company, entry and line),
 *   produccion_carga_planta and produccion_costos (no key: equal rows are
 *   legitimate).
 * - Masters, replaced whole on each close: produccion_despiece and
 *   produccion_rutas (no key until SAP confirms one) and
 *   produccion_costeo_teorico (unique by company and item).
 *
 * Quantities, hours and rates keep 6 decimals; amounts 2. Each table has its
 * stable view v_<table>, which lists its columns one by one (see the
 * MAESTROS views migration).
 */
return new class extends Migration
{
    protected $connection = 'ventas';

    /** @var array<string, list<string>> The contract columns of each table, in order. */
    private const COLUMNS = [
        'produccion_terminado' => [
            'doc_entry', 'numero_documento', 'linea', 'fecha', 'grupo', 'familia', 'codigo_articulo', 'articulo',
            'nro_ot', 'posicion', 'cantidad', 'valor',
        ],
        'produccion_carga_planta' => [
            'fecha', 'area', 'linea_producto', 'linea_negocio', 'etapa', 'puesto_trabajo', 'nro_ot', 'posicion',
            'operacion', 'codigo_articulo', 'nombre_articulo', 'unidad', 'unidades', 'unidades_no_conformes', 'horas',
            'almacen', 'estado_ot',
        ],
        'produccion_costos' => [
            'fecha', 'concepto', 'area', 'linea_producto', 'linea_negocio', 'etapa', 'material_consumido',
            'grupo_material', 'codigo_material', 'nro_ot', 'posicion', 'codigo_articulo', 'nombre_articulo',
            'puesto_trabajo', 'costo',
        ],
        'produccion_despiece' => ['padre', 'hijo', 'cantidad', 'merma'],
        'produccion_rutas' => ['codigo_articulo', 'operacion', 'area', 'puesto', 'tiempo', 'cantidad_base', 'factor_merma'],
        'produccion_costeo_teorico' => [
            'codigo_articulo', 'articulo', 'familia', 'posiciones', 'cantidad', 'material_soll', 'fabricacion_soll',
            'total_soll', 'total_ist',
        ],
    ];

    public function up(): void
    {
        // See the MAESTROS tables migration: db:wipe leaves the connection
        // disconnected and date columns need the server version.
        DB::connection()->reconnectIfMissingConnection();

        $this->create('produccion_terminado', function (Blueprint $table) {
            $table->integer('doc_entry');
            $table->integer('numero_documento');
            $table->integer('linea');
            $table->date('fecha');
            $table->string('grupo');
            $table->string('familia');
            $table->string('codigo_articulo', 50);
            $table->string('articulo')->nullable();
            $table->integer('nro_ot')->nullable();
            $table->integer('posicion')->nullable();
            $table->decimal('cantidad', 19, 6);
            $table->decimal('valor', 19, 2);
        }, function (Blueprint $table) {
            $table->unique(['empresa', 'doc_entry', 'linea']);
            // Each close deletes the company's rows from the window on.
            $table->index(['empresa', 'fecha']);
        });

        $this->create('produccion_carga_planta', function (Blueprint $table) {
            $table->date('fecha');
            $this->area($table);
            $table->string('puesto_trabajo')->nullable();
            $table->integer('nro_ot');
            $table->integer('posicion');
            $table->integer('operacion');
            $table->string('codigo_articulo', 50);
            $table->string('nombre_articulo')->nullable();
            $table->string('unidad', 100)->nullable();
            $table->decimal('unidades', 19, 6);
            $table->decimal('unidades_no_conformes', 19, 6)->nullable();
            $table->decimal('horas', 19, 6)->nullable();
            $table->string('almacen', 50)->nullable();
            // J or N.
            $table->string('estado_ot', 10)->nullable();
        }, fn (Blueprint $table) => $table->index(['empresa', 'fecha']));

        $this->create('produccion_costos', function (Blueprint $table) {
            $table->date('fecha');
            $table->string('concepto', 30);
            $this->area($table);
            $table->string('material_consumido')->nullable();
            $table->string('grupo_material')->nullable();
            $table->string('codigo_material', 50)->nullable();
            $table->integer('nro_ot');
            $table->integer('posicion');
            // The item made, not the material consumed.
            $table->string('codigo_articulo', 50);
            $table->string('nombre_articulo')->nullable();
            $table->string('puesto_trabajo')->nullable();
            $table->decimal('costo', 19, 2);
        }, fn (Blueprint $table) => $table->index(['empresa', 'fecha']));

        $this->create('produccion_despiece', function (Blueprint $table) {
            $table->string('padre', 50);
            $table->string('hijo', 50);
            $table->decimal('cantidad', 19, 6);
            $table->decimal('merma', 19, 6)->nullable();
        }, fn (Blueprint $table) => $table->index('empresa'));

        $this->create('produccion_rutas', function (Blueprint $table) {
            $table->string('codigo_articulo', 50);
            $table->integer('operacion');
            $table->string('area')->nullable();
            $table->string('puesto')->nullable();
            // Time of the operation for cantidad_base: the unit time is tiempo / cantidad_base.
            $table->decimal('tiempo', 19, 6)->nullable();
            $table->decimal('cantidad_base', 19, 6)->nullable();
            $table->decimal('factor_merma', 19, 6)->nullable();
        }, fn (Blueprint $table) => $table->index('empresa'));

        $this->create('produccion_costeo_teorico', function (Blueprint $table) {
            $table->string('codigo_articulo', 50);
            $table->string('articulo')->nullable();
            $table->string('familia');
            $table->integer('posiciones');
            $table->decimal('cantidad', 19, 6);
            $table->decimal('material_soll', 19, 2)->nullable();
            $table->decimal('fabricacion_soll', 19, 2)->nullable();
            $table->decimal('total_soll', 19, 2)->nullable();
            $table->decimal('total_ist', 19, 2)->nullable();
        }, fn (Blueprint $table) => $table->unique(['empresa', 'codigo_articulo']));
    }

    public function down(): void
    {
        foreach (array_reverse(array_keys(self::COLUMNS)) as $name) {
            DB::statement("DROP VIEW IF EXISTS v_{$name}");
            Schema::dropIfExists($name);
        }
    }

    /**
     * A table with the company, the columns of the contract, the sync time
     * and the run that loaded the row, then its keys and its stable view.
     *
     * @param  Closure(Blueprint): void  $columns
     * @param  Closure(Blueprint): mixed  $keys
     */
    private function create(string $name, Closure $columns, Closure $keys): void
    {
        Schema::create($name, function (Blueprint $table) use ($columns, $keys) {
            $table->id();
            // SGX: PRODUCCION is Segurex only.
            $table->string('empresa', 3);

            $columns($table);

            // When the run that loaded the row was applied.
            $table->dateTime('sincronizado_en');
            // The run (bases_sap) that loaded the row. Not shown in the view.
            $table->unsignedBigInteger('corrida_id')->nullable();

            $keys($table);
        });

        $columns = implode(', ', self::COLUMNS[$name]);

        DB::statement("CREATE VIEW v_{$name} AS SELECT empresa, {$columns}, sincronizado_en FROM {$name}");
    }

    /** Where a plant report or cost fact happened (contract section 12.2). */
    private function area(Blueprint $table): void
    {
        $table->string('area');
        $table->string('linea_producto');
        $table->string('linea_negocio');
        $table->string('etapa');
    }
};
