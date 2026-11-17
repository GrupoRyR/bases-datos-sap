<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * PEDIDOS in ventas_sap, next to VENTAS (docs/contrato-robot.md, section 11):
 *
 * - pedidos: one row per open customer order line, unique by company, order
 *   (doc_entry) and line. Each good close replaces every line of the
 *   company, so what was invoiced or closed in SAP disappears.
 *
 * And its stable view, v_pedidos, which lists its columns one by one (see
 * the MAESTROS views migration).
 */
return new class extends Migration
{
    protected $connection = 'ventas';

    private const COLUMNS = [
        'doc_entry', 'numero_pedido', 'linea', 'fecha_pedido', 'fecha_compromiso', 'fecha_entrega_linea', 'dias',
        'rango', 'dias_atraso', 'slp_code', 'vendedor', 'canal', 'codigo_cliente', 'cliente', 'nit', 'ciudad',
        'id_pedido_app', 'oc_cliente', 'direccion_envio', 'comentarios', 'codigo_articulo', 'descripcion',
        'linea_articulo', 'familia', 'marca', 'bodega', 'unidad', 'cantidad_pedida', 'cantidad_pendiente',
        'precio_lista', 'precio_unitario', 'descuento_documento', 'total_pendiente', 'ganancia_bruta_pendiente',
        'moneda', 'trm',
    ];

    public function up(): void
    {
        // See the MAESTROS tables migration: db:wipe leaves the connection
        // disconnected and date columns need the server version.
        DB::connection()->reconnectIfMissingConnection();

        Schema::create('pedidos', function (Blueprint $table) {
            $table->id();
            // SGX or SDC.
            $table->string('empresa', 3);

            $table->integer('doc_entry');
            $table->integer('numero_pedido');
            $table->integer('linea');
            $table->date('fecha_pedido');
            $table->date('fecha_compromiso');
            $table->date('fecha_entrega_linea')->nullable();
            // Days since the order, and the ASCII range they fall in.
            $table->integer('dias');
            $table->string('rango', 20);
            // Days since the commitment date: negative until it is due.
            $table->integer('dias_atraso');
            $table->integer('slp_code');
            $table->string('vendedor')->nullable();
            $table->string('canal')->nullable();
            $table->string('codigo_cliente', 50);
            $table->string('cliente')->nullable();
            $table->string('nit', 50)->nullable();
            $table->string('ciudad')->nullable();
            $table->string('id_pedido_app')->nullable();
            $table->string('oc_cliente')->nullable();
            $table->string('direccion_envio')->nullable();
            $table->string('comentarios')->nullable();
            $table->string('codigo_articulo', 50);
            $table->string('descripcion')->nullable();
            $table->string('linea_articulo')->nullable();
            $table->string('familia')->nullable();
            $table->string('marca')->nullable();
            $table->string('bodega', 50)->nullable();
            $table->string('unidad', 100)->nullable();
            // Sales units, the ones of the price.
            $table->decimal('cantidad_pedida', 19, 6);
            $table->decimal('cantidad_pendiente', 19, 6);
            // In the currency of the line.
            $table->decimal('precio_lista', 19, 2)->nullable();
            $table->decimal('precio_unitario', 19, 2)->nullable();
            $table->decimal('descuento_documento', 19, 6)->nullable();
            // In pesos.
            $table->decimal('total_pendiente', 19, 2);
            $table->decimal('ganancia_bruta_pendiente', 19, 2)->nullable();
            $table->string('moneda', 10)->nullable();
            $table->decimal('trm', 19, 6)->nullable();

            // When the run that loaded the line was applied.
            $table->dateTime('sincronizado_en');
            // The run (bases_sap) that loaded the line. Not shown in the view.
            $table->unsignedBigInteger('corrida_id')->nullable();

            // Also serves each close, which deletes the company's lines.
            $table->unique(['empresa', 'doc_entry', 'linea']);
        });

        $columns = implode(', ', self::COLUMNS);

        DB::statement("CREATE VIEW v_pedidos AS SELECT empresa, {$columns}, sincronizado_en FROM pedidos");
    }

    public function down(): void
    {
        DB::statement('DROP VIEW IF EXISTS v_pedidos');
        Schema::dropIfExists('pedidos');
    }
};
