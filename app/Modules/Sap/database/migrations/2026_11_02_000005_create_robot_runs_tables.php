<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Runs of the robot and the batches they hold until they close
 * (docs/contrato-robot.md, section 4). Runs are the record of every load:
 * rows, duration and errors. Batches and their keys are working data,
 * removed when the run closes, fails or expires.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('robot_runs', function (Blueprint $table) {
            $table->id();
            $table->string('conjunto', 20);
            $table->string('empresa', 3);
            // completa or solicitud.
            $table->string('tipo', 20);
            // Each part of the run and its mode: {"clientes": "cambios"}.
            $table->json('partes');
            // Ids of the update requests the run serves.
            $table->json('solicitudes');
            $table->date('fecha_corte')->nullable();
            // When the robot finished reading SAP.
            $table->dateTime('extraida_en');
            // abierta, cerrada, fallida or vencida.
            $table->string('estado', 20)->index();
            // "<conjunto>:<empresa>" while open, null after: at most one open
            // run per dataset and company, enforced by the database.
            $table->string('abierta_lock', 30)->nullable()->unique();
            // Expires if no batch arrives before this time.
            $table->dateTime('abierta_hasta');
            // The id of the robot key that started it.
            $table->string('robot_key', 32);
            // What the robot declared on close and what was received per part.
            $table->unsignedInteger('batches')->nullable();
            $table->json('filas')->nullable();
            // SAP counts and their comparison, only in full runs.
            $table->json('conteo_sap')->nullable();
            $table->json('conteo')->nullable();
            $table->unsignedInteger('lotes_rechazados')->default(0);
            // Why it failed or expired, without secrets or SAP data.
            $table->text('error')->nullable();
            $table->dateTime('aplicada_en')->nullable();
            $table->dateTime('terminada_en')->nullable();
            $table->timestamps();

            $table->index(['conjunto', 'empresa', 'estado']);
        });

        Schema::create('robot_batches', function (Blueprint $table) {
            $table->id();
            $table->foreignId('run_id')->constrained('robot_runs')->cascadeOnDelete();
            $table->unsignedInteger('batch');
            $table->string('parte', 30);
            // Of the inflated JSON body: a resend with the same body is a duplicate.
            $table->char('sha256', 64);
            $table->unsignedInteger('rows_count');
            // Validated rows as a JSON list, in the column order of the part.
            $table->longText('rows');
            $table->timestamp('created_at');

            $table->unique(['run_id', 'batch']);
        });

        // One row per key received in the run, so a repeated key is refused
        // in the batch that repeats it.
        Schema::create('robot_batch_keys', function (Blueprint $table) {
            $table->foreignId('run_id')->constrained('robot_runs')->cascadeOnDelete();
            $table->string('parte', 30);
            $table->char('key_hash', 64);

            $table->primary(['run_id', 'parte', 'key_hash']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('robot_batch_keys');
        Schema::dropIfExists('robot_batches');
        Schema::dropIfExists('robot_runs');
    }
};
