<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * The append-only audit log written through the AuditLogger contract
 * (Infrastructure\Audit\DatabaseAuditLogger). Rows are never updated or
 * deleted, so there is no updated_at.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('audit_logs', function (Blueprint $table) {
            $table->id();
            // Null for the system (robot, console, scheduler).
            $table->foreignId('user_id')->nullable()->constrained()->nullOnDelete();
            $table->string('action', 150)->index();
            $table->string('subject_type', 60)->nullable();
            // Ids may be integers or strings (SAP codes), so they are kept as text.
            $table->string('subject_id', 64)->nullable();
            $table->json('context')->nullable();
            $table->string('ip', 45)->nullable();
            $table->timestamp('created_at')->index();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('audit_logs');
    }
};
