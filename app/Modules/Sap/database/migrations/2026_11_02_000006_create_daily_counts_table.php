<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * The nightly count of each company and part (docs/plan-bases-sap.md,
 * section 6, criterion 3): rows in SAP, rows received and active rows in
 * MySQL after the full run applied. A full run that runs again the same
 * day replaces its rows. The panel reads it for the stability counter.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('daily_counts', function (Blueprint $table) {
            $table->id();
            // The day of the extraction, in Bogota.
            $table->date('fecha');
            $table->string('empresa', 3);
            $table->string('conjunto', 20);
            $table->string('parte', 30);
            $table->unsignedInteger('sap');
            $table->unsignedInteger('recibidas');
            $table->unsignedInteger('activas_mysql');
            // True when the three counts are equal.
            $table->boolean('cuadra');
            $table->foreignId('run_id')->constrained('robot_runs');
            $table->timestamps();

            $table->unique(['fecha', 'empresa', 'parte']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('daily_counts');
    }
};
