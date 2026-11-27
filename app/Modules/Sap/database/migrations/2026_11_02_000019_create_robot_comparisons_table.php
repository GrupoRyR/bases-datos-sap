<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * What the robot reports after comparing its totals of SAP with those of
 * MySQL (docs/contrato-robot.md, section 13.3), next to robot_runs. Kept for
 * the coordinator and the panel; never applied to the data.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('robot_comparisons', function (Blueprint $table) {
            $table->id();
            $table->string('conjunto', 20);
            $table->string('empresa', 3);
            // The VENTAS posting dates compared, both included; null elsewhere.
            $table->date('desde')->nullable();
            $table->date('hasta')->nullable();
            $table->boolean('cuadra');
            // [{"clave", "campo", "sap", "mysql"}], empty when it matches.
            $table->json('diferencias');
            // When the robot compared, in Bogota.
            $table->dateTime('comparada_en');
            // The id of the robot key that sent it.
            $table->string('robot_key', 32);
            $table->timestamp('created_at');

            // One comparison per robot key and moment: a retry after a lost
            // answer stores nothing new (section 13.3). It also serves the
            // latest comparison of a company and dataset.
            $table->unique(['conjunto', 'empresa', 'comparada_en', 'robot_key']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('robot_comparisons');
    }
};
