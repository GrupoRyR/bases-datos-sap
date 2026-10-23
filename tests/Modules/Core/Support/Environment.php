<?php

namespace Tests\Modules\Core\Support;

use Closure;

/**
 * Runs code with environment variables set as a real .env would set them,
 * whatever the local .env says, and restores them afterwards. Call
 * refreshApplication() inside the callback so config files read them again.
 */
final class Environment
{
    /**
     * @param  array<string, string>  $variables
     */
    public static function with(array $variables, Closure $callback): void
    {
        $previous = [];

        foreach ($variables as $name => $value) {
            $previous[$name] = [
                'server' => $_SERVER[$name] ?? null,
                'env' => $_ENV[$name] ?? null,
                'getenv' => getenv($name),
            ];

            $_SERVER[$name] = $_ENV[$name] = $value;
            putenv("{$name}={$value}");
        }

        try {
            $callback();
        } finally {
            foreach ($previous as $name => $values) {
                self::restore($name, $values['server'], $values['env'], $values['getenv']);
            }
        }
    }

    private static function restore(string $name, mixed $server, mixed $env, string|false $getenv): void
    {
        if ($server === null) {
            unset($_SERVER[$name]);
        } else {
            $_SERVER[$name] = $server;
        }

        if ($env === null) {
            unset($_ENV[$name]);
        } else {
            $_ENV[$name] = $env;
        }

        putenv($getenv === false ? $name : "{$name}={$getenv}");
    }
}
