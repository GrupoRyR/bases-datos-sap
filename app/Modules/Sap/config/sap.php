<?php

return [

    /*
    |--------------------------------------------------------------------------
    | Robot
    |--------------------------------------------------------------------------
    |
    | What the robot sends and how it is checked (docs/contrato-robot.md,
    | sections 2 and 3). Keys come from ROBOT_HMAC_KEYS as "id:secret"
    | pairs separated by commas; to rotate, add the new pair next to the old
    | one, move the robot to it and then remove the old one.
    |
    */

    'robot' => [
        'keys' => (string) env('ROBOT_HMAC_KEYS', ''),

        // A timestamp further than this from the server clock is rejected.
        'clock_skew_seconds' => 300,

        // A nonce cannot be reused by the same key within this window.
        'nonce_ttl_seconds' => 600,

        // As the body travels (gzip bytes when compressed) and once inflated.
        'max_body_bytes' => 10 * 1024 * 1024,
        'max_decompressed_bytes' => 40 * 1024 * 1024,

        // Per IP; beyond it, 429 with Retry-After.
        'requests_per_minute' => 120,
    ],

];
