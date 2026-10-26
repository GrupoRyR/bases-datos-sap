<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * The nonces of signed robot requests (docs/contrato-robot.md, section 3).
 * A nonce is stored only after its signature checks out, and rows older
 * than the replay window are pruned by the scheduler.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('robot_nonces', function (Blueprint $table) {
            $table->id();
            // The id of the key in ROBOT_HMAC_KEYS, never the secret.
            $table->string('key_id', 32);
            $table->char('nonce', 32);
            $table->timestamp('created_at')->index();

            $table->unique(['key_id', 'nonce']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('robot_nonces');
    }
};
