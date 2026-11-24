<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * The last day of a historical VENTAS run's range (docs/contrato-robot.md,
 * sections 4.1 and 10.4): its batches never bring a later line, and its
 * close inserts only into that range. Null in every other run.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('robot_runs', function (Blueprint $table) {
            $table->date('ventana_hasta')->nullable()->after('ventana_desde');
        });
    }

    public function down(): void
    {
        Schema::table('robot_runs', function (Blueprint $table) {
            $table->dropColumn('ventana_hasta');
        });
    }
};
