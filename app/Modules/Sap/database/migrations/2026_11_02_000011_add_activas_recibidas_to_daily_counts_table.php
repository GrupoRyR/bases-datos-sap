<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Adds activas_recibidas to the nightly count (docs/contrato-robot.md,
 * section 4.3): the received rows that are active, which is what the active
 * rows in MySQL must equal because SAP also sends the inactive ones. It is
 * nullable: the counts saved before it existed keep null and the panel
 * only reads cuadra.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('daily_counts', function (Blueprint $table) {
            $table->unsignedInteger('activas_recibidas')->nullable()->after('recibidas');
        });
    }

    public function down(): void
    {
        Schema::table('daily_counts', function (Blueprint $table) {
            $table->dropColumn('activas_recibidas');
        });
    }
};
