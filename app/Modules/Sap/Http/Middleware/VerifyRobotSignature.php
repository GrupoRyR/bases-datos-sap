<?php

namespace App\Modules\Sap\Http\Middleware;

use App\Modules\Sap\Domain\Robot\RobotSignature;
use App\Modules\Sap\Infrastructure\Robot\NonceStore;
use Closure;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Symfony\Component\HttpFoundation\Response;

/**
 * Checks the HMAC-SHA256 signature of a robot request before anything reads
 * or inflates its body (docs/contrato-robot.md, section 3). Every failure
 * gets the same 401 and is logged with its reason, the key id and the IP.
 * On success the key id is in the "robot_key" request attribute.
 *
 * A query string gets 400 before anything else (contract section 2): the
 * signature does not cover it, and input() would merge its values into the
 * body's missing keys.
 */
final class VerifyRobotSignature
{
    public function __construct(private readonly NonceStore $nonces) {}

    public function handle(Request $request, Closure $next): Response
    {
        $key = (string) $request->header('X-Robot-Key', '');
        $timestamp = (string) $request->header('X-Robot-Timestamp', '');
        $nonce = (string) $request->header('X-Robot-Nonce', '');
        $signature = (string) $request->header('X-Robot-Signature', '');

        if ($request->getQueryString() !== null || $request->query->count() > 0) {
            $this->reject($request, 'query_string', $key);

            return response()->json(['message' => 'Las rutas del robot no llevan query string.'], 400);
        }

        $reason = match (true) {
            ! preg_match('/^[A-Za-z0-9_-]{1,32}$/', $key),
            ! preg_match('/^\d{1,12}$/', $timestamp),
            ! preg_match('/^[0-9a-f]{32}$/', $nonce),
            ! preg_match('/^sha256=[0-9a-f]{64}$/', $signature) => 'malformed_headers',
            ($secret = $this->secretFor($key)) === null => 'unknown_key',
            abs(now()->getTimestamp() - (int) $timestamp) > (int) config('sap.robot.clock_skew_seconds') => 'stale_timestamp',
            ! RobotSignature::matches($signature, $secret, (int) $timestamp, $nonce, '/'.ltrim($request->path(), '/'), $request->getContent()) => 'signature_mismatch',
            // Only now, so a forged request cannot burn the robot's nonces.
            ! $this->nonces->remember($key, $nonce) => 'replayed_nonce',
            default => null,
        };

        if ($reason !== null) {
            $this->reject($request, $reason, $key);

            return response()->json(['message' => 'Firma inválida.'], 401);
        }

        $request->attributes->set('robot_key', $key);

        return $next($request);
    }

    /**
     * Logs why a request was turned away, with the key id only if it is well formed.
     */
    private function reject(Request $request, string $reason, string $key): void
    {
        Log::warning('sap.robot.signature_rejected', [
            'reason' => $reason,
            'key' => preg_match('/^[A-Za-z0-9_-]{1,32}$/', $key) ? $key : null,
            'ip' => $request->ip(),
        ]);
    }

    /**
     * The secret of a key id in ROBOT_HMAC_KEYS ("id:secret,id2:secret2").
     */
    private function secretFor(string $key): ?string
    {
        foreach (explode(',', (string) config('sap.robot.keys')) as $pair) {
            [$id, $secret] = array_pad(explode(':', trim($pair), 2), 2, '');

            if ($id === $key && $secret !== '') {
                return $secret;
            }
        }

        return null;
    }
}
