<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Adds fecha_corte to the current CARTERA (docs/contrato-robot.md, section
 * 6): the day its overdue days are counted to, the Bogota date of the run's
 * extraida_en. It is not the run's fecha_corte, which only the photos keep.
 * v_cartera is recreated with it at the end, after sincronizado_en. The
 * column is nullable: the lines stored before it carry null until the next
 * close replaces them.
 */
return new class extends Migration
{
    protected $connection = 'cartera';

    private const COLUMNS = [
        'codigo_sn', 'slp_code', 'email_asesor', 'nombre_sn', 'nit', 'grupo', 'municipio', 'cuenta_visible',
        'tipo_doc', 'documento', 'documento_base', 'referencia_1', 'no_referencia', 'asesor', 'total_plazos',
        'no_plazo', 'condicion_pago', 'fecha_contabilizacion', 'fecha_vencimiento', 'fecha_documento', 'dias',
        'limite_credito', 'importe_original', 'base_gravable', 'saldo_base', 'saldo_vencido', 'valor_abonado',
        'sin_vencer', 'valor_cheques', 'd_0_30', 'd_31_60', 'd_61_90', 'd_91_120', 'd_121_150', 'd_151_180',
        'd_mas_180', 'saldo', 'rango',
    ];

    public function up(): void
    {
        DB::connection()->reconnectIfMissingConnection();

        Schema::table('cartera', function (Blueprint $table) {
            $table->date('fecha_corte')->nullable();
        });

        $this->recreateView([...self::COLUMNS, 'sincronizado_en', 'fecha_corte']);
    }

    public function down(): void
    {
        DB::connection()->reconnectIfMissingConnection();

        $this->recreateView([...self::COLUMNS, 'sincronizado_en']);

        Schema::table('cartera', function (Blueprint $table) {
            $table->dropColumn('fecha_corte');
        });
    }

    /**
     * @param  list<string>  $columns
     */
    private function recreateView(array $columns): void
    {
        $list = implode(', ', ['empresa', ...$columns]);

        DB::statement('DROP VIEW IF EXISTS v_cartera');
        DB::statement("CREATE VIEW v_cartera AS SELECT {$list} FROM cartera");
    }
};
