<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * CARTERA in cartera_sap (docs/plan-bases-sap.md, section 4; columns from
 * docs/contrato-robot.md, section 6, the same as the gestor de cartera):
 *
 * - cartera: the current receivables. Each good close replaces the whole
 *   company in one transaction, so it is never left empty.
 * - cartera_fotos: one photo per company and cut-off date, from the nightly
 *   full run. Photos are never deleted.
 *
 * And their stable views, v_cartera and v_cartera_fotos, which list their
 * columns one by one (see the MAESTROS views migration).
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
        Schema::create('cartera', function (Blueprint $table) {
            $this->receivables($table);
            $table->index(['empresa', 'slp_code']);
            $table->index(['empresa', 'codigo_sn']);
        });

        Schema::create('cartera_fotos', function (Blueprint $table) {
            $this->receivables($table, photo: true);
            $table->index(['empresa', 'fecha_corte']);
        });

        $columns = implode(', ', self::COLUMNS);

        DB::statement("CREATE VIEW v_cartera AS SELECT empresa, {$columns}, sincronizado_en FROM cartera");
        DB::statement("CREATE VIEW v_cartera_fotos AS SELECT empresa, fecha_corte, {$columns}, sincronizado_en FROM cartera_fotos");
    }

    public function down(): void
    {
        DB::statement('DROP VIEW IF EXISTS v_cartera_fotos');
        DB::statement('DROP VIEW IF EXISTS v_cartera');
        Schema::dropIfExists('cartera_fotos');
        Schema::dropIfExists('cartera');
    }

    /**
     * The receivable columns plus the company, the run and the sync time; a
     * photo also carries its cut-off date.
     */
    private function receivables(Blueprint $table, bool $photo = false): void
    {
        $table->id();
        // SGX or SDC.
        $table->string('empresa', 3);

        if ($photo) {
            // The day the photo stands for: the day before the nightly run.
            $table->date('fecha_corte');
        }

        $table->string('codigo_sn', 50);
        $table->integer('slp_code')->nullable();
        $table->string('email_asesor')->nullable();
        $table->string('nombre_sn')->nullable();
        $table->string('nit', 50)->nullable();
        $table->string('grupo')->nullable();
        $table->string('municipio')->nullable();
        $table->string('cuenta_visible')->nullable();
        $table->string('tipo_doc', 50)->nullable();
        $table->string('documento', 50);
        $table->string('documento_base', 50)->nullable();
        $table->string('referencia_1')->nullable();
        $table->string('no_referencia')->nullable();
        $table->string('asesor')->nullable();
        $table->integer('total_plazos')->nullable();
        $table->integer('no_plazo')->nullable();
        $table->string('condicion_pago')->nullable();
        $table->date('fecha_contabilizacion')->nullable();
        $table->date('fecha_vencimiento');
        $table->date('fecha_documento')->nullable();
        $table->integer('dias');

        foreach (['limite_credito', 'importe_original', 'base_gravable', 'saldo_base', 'saldo_vencido',
            'valor_abonado', 'sin_vencer', 'valor_cheques', 'd_0_30', 'd_31_60', 'd_61_90', 'd_91_120',
            'd_121_150', 'd_151_180', 'd_mas_180'] as $amount) {
            $table->decimal($amount, 19, 2)->nullable();
        }

        $table->decimal('saldo', 19, 2);
        $table->string('rango', 50)->nullable();

        // When the run that loaded the line was applied.
        $table->dateTime('sincronizado_en');
        // The run (bases_sap) that loaded the line. Not shown in the views.
        $table->unsignedBigInteger('corrida_id')->nullable();
    }
};
