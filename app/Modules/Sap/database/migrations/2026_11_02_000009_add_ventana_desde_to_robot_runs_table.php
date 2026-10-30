<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * The first day of a VENTAS run's window (docs/contrato-robot.md, sections
 * 4.1 and 10.1): its batches never bring an earlier line, and its close
 * replaces only the company's lines from that day on. Null in the other
 * datasets.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('robot_runs', function (Blueprint $table) {
            $table->date('ventana_desde')->nullable()->after('fecha_corte');
        });
    }

    public function down(): void
    {
        Schema::table('robot_runs', function (Blueprint $table) {
            $table->dropColumn('ventana_desde');
        });
    }
};
