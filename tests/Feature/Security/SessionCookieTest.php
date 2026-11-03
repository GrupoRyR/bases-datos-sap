<?php

/*
| The session cookie goes only over https when the app is served over https
| (audit S-03); local http keeps working. The test reads config/session.php
| again with the given variables, so a cached config or the .env of the
| checkout does not change the result.
*/

/**
 * config/session.php as it loads with only these APP_URL and
 * SESSION_SECURE_COOKIE values; the environment is restored afterwards.
 *
 * @param  array<string, string>  $env
 * @return array<string, mixed>
 */
function sessionConfigWith(array $env): array
{
    $keys = ['APP_URL', 'SESSION_SECURE_COOKIE'];
    $saved = [];

    foreach ($keys as $key) {
        $saved[$key] = [$_SERVER[$key] ?? null, $_ENV[$key] ?? null, getenv($key)];
        unset($_SERVER[$key], $_ENV[$key]);
        putenv($key);
    }

    foreach ($env as $key => $value) {
        $_SERVER[$key] = $_ENV[$key] = $value;
        putenv("{$key}={$value}");
    }

    try {
        return require config_path('session.php');
    } finally {
        foreach ($saved as $key => [$server, $environment, $process]) {
            unset($_SERVER[$key], $_ENV[$key]);
            putenv($key);

            if ($server !== null) {
                $_SERVER[$key] = $server;
            }

            if ($environment !== null) {
                $_ENV[$key] = $environment;
            }

            if ($process !== false) {
                putenv("{$key}={$process}");
            }
        }
    }
}

it('marks the session cookie secure by default only when the app runs on https', function (array $env, bool $secure) {
    expect(sessionConfigWith($env)['secure'])->toBe($secure);
})->with([
    'https' => [['APP_URL' => 'https://bases-sap.example.com'], true],
    'http, as in local' => [['APP_URL' => 'http://localhost:8000'], false],
    'no APP_URL' => [[], false],
]);

it('lets SESSION_SECURE_COOKIE override the default', function (array $env, bool $secure) {
    expect(sessionConfigWith($env)['secure'])->toBe($secure);
})->with([
    'off on https' => [['APP_URL' => 'https://bases-sap.example.com', 'SESSION_SECURE_COOKIE' => 'false'], false],
    'on over http' => [['APP_URL' => 'http://localhost:8000', 'SESSION_SECURE_COOKIE' => 'true'], true],
]);
