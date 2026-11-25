<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Adds kilos (the weight of the line, "Tot KG" of AnálisisVentas-1, negative
 * on credit notes) to VENTAS (docs/contrato-robot.md, section 10) and
 * recreates v_ventas with it at the end, after sincronizado_en: a view only
 * grows at the end. The column is nullable: the batches that arrive before
 * the robot sends it, and the lines already stored, carry null until the
 * kilos run fills them.
 */
return new class extends Migration
{
    protected $connection = 'ventas';

    private const COLUMNS = [
        'tipo_objeto', 'doc_entry', 'numero_documento', 'linea', 'clase_documento', 'estado_documento',
        'fecha_documento', 'fecha_contabilizacion', 'slp_code', 'vendedor', 'canal', 'codigo_cliente', 'cliente',
        'nit', 'ciudad', 'pedido', 'id_pedido_app', 'oc_cliente', 'ciudad_envio', 'direccion_envio', 'marca',
        'familia', 'codigo_articulo', 'descripcion', 'cantidad', 'costo_unitario', 'costo_total', 'precio_lista',
        'precio_unitario', 'total', 'iva', 'ganancia_bruta', 'moneda', 'trm', 'comentarios',
    ];

    public function up(): void
    {
        DB::connection()->reconnectIfMissingConnection();

        Schema::table('ventas', function (Blueprint $table) {
            $table->decimal('kilos', 19, 6)->nullable();
        });

        $this->recreateView([...self::COLUMNS, 'sincronizado_en', 'kilos']);
    }

    public function down(): void
    {
        DB::connection()->reconnectIfMissingConnection();

        $this->recreateView([...self::COLUMNS, 'sincronizado_en']);

        Schema::table('ventas', function (Blueprint $table) {
            $table->dropColumn('kilos');
        });
    }

    /**
     * @param  list<string>  $columns
     */
    private function recreateView(array $columns): void
    {
        $list = implode(', ', ['empresa', ...$columns]);

        DB::statement('DROP VIEW IF EXISTS v_ventas');
        DB::statement("CREATE VIEW v_ventas AS SELECT {$list} FROM ventas");
    }
};
