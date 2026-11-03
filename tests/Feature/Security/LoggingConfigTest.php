<?php

/*
| By default the log rotates daily, keeps 14 days and records warnings and
| up (audit S-05): a single debug file grows forever and keeps whatever it
| got. The test reads config/logging.php again with the logging variables
| cleared, so a cached config or the .env of the checkout does not change it.
*/

/**
 * config/logging.php as it loads with only these logging variables; the
 * environment is restored afterwards.
 *
 * @param  array<string, string>  $env
 * @return array<string, mixed>
 */
function loggingConfigWith(array $env): array
{
    $keys = ['LOG_CHANNEL', 'LOG_STACK', 'LOG_LEVEL', 'LOG_DAILY_DAYS'];
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
        return require config_path('logging.php');
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

it('rotates the log daily for 14 days at warning level by default', function () {
    $config = loggingConfigWith([]);

    expect($config['default'])->toBe('stack')
        ->and($config['channels']['stack']['channels'])->toBe(['daily'])
        ->and($config['channels']['daily']['level'])->toBe('warning')
        ->and($config['channels']['daily']['max_files'])->toBe(14)
        ->and($config['channels']['single']['level'])->toBe('warning');
});

it('lets LOG_STACK and LOG_LEVEL override the defaults', function () {
    $config = loggingConfigWith(['LOG_STACK' => 'single', 'LOG_LEVEL' => 'debug']);

    expect($config['channels']['stack']['channels'])->toBe(['single'])
        ->and($config['channels']['single']['level'])->toBe('debug')
        ->and($config['channels']['daily']['level'])->toBe('debug');
});
