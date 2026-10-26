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

    /*
    |--------------------------------------------------------------------------
    | Apps
    |--------------------------------------------------------------------------
    |
    | The API the apps call with their own key (contract section 7.4).
    |
    */

    'apps' => [
        // Per key; beyond it, 429 with Retry-After.
        'requests_per_minute' => 60,
    ],

    /*
    |--------------------------------------------------------------------------
    | Update requests
    |--------------------------------------------------------------------------
    |
    | How requests wait (docs/contrato-robot.md, section 7.2). The blocked
    | slots are the times the other robots use the VPN, in Bogota, from
    | BASES_SAP_FRANJAS_BLOQUEADAS; a request that falls this many minutes
    | or less before or after one runs at the end of the window.
    |
    */

    'requests' => [
        'blocked_slots' => (string) env('BASES_SAP_FRANJAS_BLOQUEADAS', '00:00,05:00,06:00,12:00,12:30'),
        'slot_margin_minutes' => 15,

        // A request waits this long after a sister that finished well.
        'wait_after_done_minutes' => 3,

        // A taken request that has not finished by then expires.
        'taken_expires_minutes' => 30,
    ],

];
