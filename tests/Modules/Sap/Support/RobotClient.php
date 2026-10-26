<?php

namespace Tests\Modules\Sap\Support;

use Illuminate\Testing\TestResponse;
use Tests\TestCase;

/**
 * Sends requests the way the robot does (docs/contrato-robot.md, sections
 * 2 and 3): JSON body, optional gzip, and the four X-Robot-* headers signed
 * with HMAC-SHA256 over the body exactly as it travels.
 */
final class RobotClient
{
    public const KEY = 'r2026a';

    public const SECRET = 'robot-secreto-de-prueba';

    /** Registers the test key as ROBOT_HMAC_KEYS would. */
    public static function configure(): void
    {
        config(['sap.robot.keys' => self::KEY.':'.self::SECRET]);
    }

    public static function sign(string $secret, int $timestamp, string $nonce, string $path, string $body): string
    {
        $canonical = implode("\n", [$timestamp, $nonce, 'POST', $path, hash('sha256', $body)]);

        return 'sha256='.hash_hmac('sha256', $canonical, $secret);
    }

    /**
     * POSTs a signed request. $headers overrides or removes (null) any header
     * after signing, to build broken requests.
     *
     * @param  array<string, mixed>|string  $body
     * @param  array<string, string|null>  $headers
     */
    public static function post(TestCase $test, string $path, array|string $body = [], bool $gzip = false, array $headers = [], ?int $timestamp = null, ?string $nonce = null): TestResponse
    {
        $json = is_string($body) ? $body : (string) json_encode((object) $body, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        $wire = $gzip ? (string) gzencode($json) : $json;
        $timestamp ??= time();
        $nonce ??= bin2hex(random_bytes(16));

        $all = array_merge([
            'Content-Type' => 'application/json',
            'Content-Encoding' => $gzip ? 'gzip' : null,
            'X-Robot-Key' => self::KEY,
            'X-Robot-Timestamp' => (string) $timestamp,
            'X-Robot-Nonce' => $nonce,
            'X-Robot-Signature' => self::sign(self::SECRET, $timestamp, $nonce, $path, $wire),
        ], $headers);

        $server = [];

        foreach (array_filter($all, fn (?string $value): bool => $value !== null) as $name => $value) {
            $key = strtoupper(str_replace('-', '_', $name));
            $server[in_array($key, ['CONTENT_TYPE', 'CONTENT_LENGTH'], true) ? $key : 'HTTP_'.$key] = $value;
        }

        return $test->call('POST', $path, [], [], [], $server, $wire);
    }
}
