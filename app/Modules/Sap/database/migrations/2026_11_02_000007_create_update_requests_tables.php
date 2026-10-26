<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Update requests (docs/contrato-robot.md, section 7) and the apps that
 * may ask for them with their own key.
 */
return new class extends Migration
{
    public function up(): void
    {
        // Apps connected to the API. Only the SHA-256 of the key is kept:
        // the key is shown once and can be revoked from the panel.
        Schema::create('client_apps', function (Blueprint $table) {
            $table->id();
            $table->string('nombre', 100)->unique();
            $table->char('key_hash', 64)->unique();
            // The first characters of the key, to recognize it in the panel.
            $table->string('key_prefix', 16);
            $table->dateTime('revoked_at')->nullable();
            $table->dateTime('last_used_at')->nullable();
            $table->timestamps();
        });

        Schema::create('update_requests', function (Blueprint $table) {
            $table->id();
            $table->string('empresa', 3);
            $table->string('conjunto', 20);
            // A RequestScope of MAESTROS; null asks for the whole dataset.
            $table->string('parte', 30)->nullable();
            // pendiente, en_cola, tomada, terminada, fallida or vencida.
            $table->string('estado', 20);
            // When it may run; null while it waits for a sister being served.
            $table->dateTime('correr_desde')->nullable();
            $table->dateTime('tomada_en')->nullable();
            $table->dateTime('terminada_en')->nullable();
            $table->text('error')->nullable();
            // The run that served it.
            $table->foreignId('run_id')->nullable()->constrained('robot_runs')->nullOnDelete();
            // created_at is when it was asked for (solicitada_en).
            $table->timestamps();

            $table->index(['empresa', 'conjunto', 'estado']);
            $table->index(['estado', 'correr_desde']);
        });

        // Who asked: every app and person that created or joined a request.
        Schema::create('update_request_requesters', function (Blueprint $table) {
            $table->id();
            $table->foreignId('update_request_id')->constrained()->cascadeOnDelete();
            // Null when the request came from the panel.
            $table->foreignId('client_app_id')->nullable()->constrained()->nullOnDelete();
            $table->string('correo');
            $table->string('nombre')->nullable();
            $table->timestamp('created_at');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('update_request_requesters');
        Schema::dropIfExists('update_requests');
        Schema::dropIfExists('client_apps');
    }
};
