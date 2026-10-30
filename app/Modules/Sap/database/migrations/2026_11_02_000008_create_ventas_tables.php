<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * VENTAS in ventas_sap (docs/plan-bases-sap.md, section 4; columns from
 * docs/contrato-robot.md, section 10, the same as the gestor de cartera):
 *
 * - ventas: one row per invoice or credit note line, unique by company,
 *   document type, document and line. Each good close replaces only the
 *   company's rows from the run's window on; earlier rows are the frozen
 *   history Comisiones reads and are never touched.
 *
 * And its stable view, v_ventas, which lists its columns one by one (see
 * the MAESTROS views migration).
 */
return new class extends Migration
{
    protected $connection = 'ventas';

    private const COLUMNS = [
        'tipo_objeto', 'doc_entry', 'numero_documento', 'linea', 'clase_documento', 'estado_documento',
        'fecha_documento', 'fecha_contabilizacion', 'slp_code', 'vendedor', 'canal', 'codigo_cliente', 'cliente',
        'nit', 'ciudad', 'pedido', 'id_pedido_app', 'oc_cliente', 'ciudad_envio', 'direccion_envio', 'marca',
        'familia', 'codigo_articulo', 'descripcion', 'cantidad', 'costo_unitario', 'costo_total', 'precio_lista',
        'precio_unitario', 'total', 'iva', 'moneda', 'trm', 'comentarios',
    ];

    public function up(): void
    {
        // See the MAESTROS tables migration: db:wipe leaves the connection
        // disconnected and date columns need the server version.
        DB::connection()->reconnectIfMissingConnection();

        Schema::create('ventas', function (Blueprint $table) {
            $table->id();
            // SGX or SDC.
            $table->string('empresa', 3);

            // 13 invoice (and debit note), 14 credit note.
            $table->integer('tipo_objeto');
            $table->integer('doc_entry');
            $table->integer('numero_documento');
            $table->integer('linea');
            $table->string('clase_documento', 20);
            $table->string('estado_documento', 20);
            // TaxDate, reference only.
            $table->date('fecha_documento');
            // DocDate: the month of the sale and the column of the window.
            $table->date('fecha_contabilizacion');
            $table->integer('slp_code');
            $table->string('vendedor')->nullable();
            $table->string('canal')->nullable();
            $table->string('codigo_cliente', 50);
            $table->string('cliente')->nullable();
            $table->string('nit', 50)->nullable();
            $table->string('ciudad')->nullable();
            $table->string('pedido')->nullable();
            $table->string('id_pedido_app')->nullable();
            $table->string('oc_cliente')->nullable();
            $table->string('ciudad_envio')->nullable();
            $table->string('direccion_envio')->nullable();
            $table->string('marca')->nullable();
            $table->string('familia')->nullable();
            $table->string('codigo_articulo', 50)->nullable();
            $table->string('descripcion')->nullable();
            $table->decimal('cantidad', 19, 6);
            $table->decimal('costo_unitario', 19, 2)->nullable();
            $table->decimal('costo_total', 19, 2)->nullable();
            $table->decimal('precio_lista', 19, 2)->nullable();
            $table->decimal('precio_unitario', 19, 2)->nullable();
            $table->decimal('total', 19, 2);
            $table->decimal('iva', 19, 2)->nullable();
            $table->string('moneda', 10)->nullable();
            $table->decimal('trm', 19, 6)->nullable();
            $table->string('comentarios')->nullable();

            // When the run that loaded the line was applied.
            $table->dateTime('sincronizado_en');
            // The run (bases_sap) that loaded the line. Not shown in the view.
            $table->unsignedBigInteger('corrida_id')->nullable();

            $table->unique(['empresa', 'tipo_objeto', 'doc_entry', 'linea']);
            // Each close deletes the company's window; Comisiones reads by month.
            $table->index(['empresa', 'fecha_contabilizacion']);
        });

        $columns = implode(', ', self::COLUMNS);

        DB::statement("CREATE VIEW v_ventas AS SELECT empresa, {$columns}, sincronizado_en FROM ventas");
    }

    public function down(): void
    {
        DB::statement('DROP VIEW IF EXISTS v_ventas');
        Schema::dropIfExists('ventas');
    }
};
