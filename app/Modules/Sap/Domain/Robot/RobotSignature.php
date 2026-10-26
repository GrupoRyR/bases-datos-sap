<?php

namespace App\Modules\Sap\Domain\Robot;

/**
 * The HMAC-SHA256 signature of a robot request (docs/contrato-robot.md,
 * section 3): timestamp, nonce, method, path and the SHA-256 of the body as
 * it travels, joined by "\n" with no trailing newline.
 */
final class RobotSignature
{
    public static function sign(string $secret, int $timestamp, string $nonce, string $path, string $body): string
    {
        $canonical = implode("\n", [$timestamp, $nonce, 'POST', $path, hash('sha256', $body)]);

        return 'sha256='.hash_hmac('sha256', $canonical, $secret);
    }

    /**
     * Compares in constant time, so the answer leaks nothing about the secret.
     */
    public static function matches(string $signature, string $secret, int $timestamp, string $nonce, string $path, string $body): bool
    {
        return hash_equals(self::sign($secret, $timestamp, $nonce, $path, $body), $signature);
    }
}
