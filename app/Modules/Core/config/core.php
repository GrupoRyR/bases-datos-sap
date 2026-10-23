<?php

return [

    /*
    |--------------------------------------------------------------------------
    | Bootstrap admins
    |--------------------------------------------------------------------------
    |
    | E-mails (comma-separated in CORE_ADMIN_EMAILS) that get the admin_ti
    | role when they sign in with Microsoft, so the first admin needs no
    | console. The list never downgrades anyone: removing an e-mail keeps its
    | role until "php artisan core:rol <correo> ninguno".
    |
    */

    'admins' => array_values(array_filter(
        array_map(
            fn (string $email): string => mb_strtolower(trim($email)),
            explode(',', (string) env('CORE_ADMIN_EMAILS', '')),
        ),
        fn (string $email): bool => $email !== '',
    )),

];
