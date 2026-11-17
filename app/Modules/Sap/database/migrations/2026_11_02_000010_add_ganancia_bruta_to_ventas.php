<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Adds ganancia_bruta (INV1/RIN1.GrssProfit, negative on credit notes) to
 * VENTAS (docs/contrato-robot.md, section 10) and recreates v_ventas so it
 * exposes it, right after iva. The column is nullable: the batches that
 * arrive before the robot sends it, and the lines already stored, carry null.
 */
return new class extends Migration
{
    protected $connection = 'ventas';

    private const COLUMNS_BEFORE = [
        'tipo_objeto', 'doc_entry', 'numero_documento', 'linea', 'clase_documento', 'estado_documento',
        'fecha_documento', 'fecha_contabilizacion', 'slp_code', 'vendedor', 'canal', 'codigo_cliente', 'cliente',
        'nit', 'ciudad', 'pedido', 'id_pedido_app', 'oc_cliente', 'ciudad_envio', 'direccion_envio', 'marca',
        'familia', 'codigo_articulo', 'descripcion', 'cantidad', 'costo_unitario', 'costo_total', 'precio_lista',
        'precio_unitario', 'total', 'iva',
    ];

    private const COLUMNS_AFTER = ['moneda', 'trm', 'comentarios'];

    public function up(): void
    {
        DB::connection()->reconnectIfMissingConnection();

        Schema::table('ventas', function (Blueprint $table) {
            $table->decimal('ganancia_bruta', 19, 2)->nullable()->after('iva');
        });

        $this->recreateView([...self::COLUMNS_BEFORE, 'ganancia_bruta', ...self::COLUMNS_AFTER]);
    }

    public function down(): void
    {
        DB::connection()->reconnectIfMissingConnection();

        $this->recreateView([...self::COLUMNS_BEFORE, ...self::COLUMNS_AFTER]);

        Schema::table('ventas', function (Blueprint $table) {
            $table->dropColumn('ganancia_bruta');
        });
    }

    /**
     * @param  list<string>  $columns
     */
    private function recreateView(array $columns): void
    {
        $list = implode(', ', $columns);

        DB::statement('DROP VIEW IF EXISTS v_ventas');
        DB::statement("CREATE VIEW v_ventas AS SELECT empresa, {$list}, sincronizado_en FROM ventas");
    }
};
