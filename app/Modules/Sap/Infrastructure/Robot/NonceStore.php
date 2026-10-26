<?php

namespace App\Modules\Sap\Infrastructure\Robot;

use Illuminate\Support\Facades\DB;

/**
 * The nonces already used by each robot key (table robot_nonces). The
 * unique index on key and nonce makes remembering and checking one atomic.
 */
final class NonceStore
{
    /**
     * Records the nonce; false when the key already used it.
     */
    public function remember(string $key, string $nonce): bool
    {
        return DB::table('robot_nonces')->insertOrIgnore([
            'key_id' => $key,
            'nonce' => $nonce,
            'created_at' => now(),
        ]) === 1;
    }

    /**
     * Forgets nonces past the replay window: an older request already fails
     * the timestamp check. Returns how many were removed.
     */
    public function prune(): int
    {
        return DB::table('robot_nonces')
            ->where('created_at', '<', now()->subSeconds((int) config('sap.robot.nonce_ttl_seconds')))
            ->delete();
    }
}
