<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * The people of the TI panel. They sign in with Microsoft Entra ID only, so
 * there is no password. Users are never deleted: they are deactivated.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('users', function (Blueprint $table) {
            $table->id();
            $table->string('name');
            // Always in lowercase (User::normalizeEmail()).
            $table->string('email')->unique();
            // The object id (oid) of the account in Entra ID, set at the first sign-in.
            $table->string('microsoft_id')->nullable()->unique();
            // A Role value (admin_ti, consulta); null until TI gives one.
            $table->string('role', 30)->nullable();
            $table->boolean('is_active')->default(true);
            $table->timestamp('last_signed_in_at')->nullable();
            $table->rememberToken();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('users');
    }
};
