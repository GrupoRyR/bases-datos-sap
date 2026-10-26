<?php

namespace App\Modules\Sap\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\InputBag;
use Symfony\Component\HttpFoundation\Response;

/**
 * Inflates a gzip body and parses its JSON object once the signature has
 * checked out (docs/contrato-robot.md, section 2). The inflated JSON text
 * stays in the "robot_body" attribute, so a batch can be compared by its
 * SHA-256 whether or not it traveled compressed.
 */
final class DecodeRobotBody
{
    /** Bytes of compressed input inflated per step, to stop a gzip bomb early. */
    private const CHUNK = 8192;

    public function handle(Request $request, Closure $next): Response
    {
        $limit = (int) config('sap.robot.max_decompressed_bytes');
        $encoding = strtolower(trim((string) $request->header('Content-Encoding', '')));
        $body = $request->getContent();

        if (! $request->isJson() || ! in_array($encoding, ['', 'identity', 'gzip'], true)) {
            return response()->json(['message' => 'El cuerpo debe ser JSON, sin comprimir o en gzip.'], 415);
        }

        if ($encoding === 'gzip') {
            $body = $this->inflate($body, $limit);

            if ($body === false) {
                return response()->json(['message' => 'El cuerpo gzip está dañado.'], 400);
            }
        }

        if (strlen($body) > $limit) {
            return response()->json(['message' => 'El cuerpo es demasiado grande.'], 413);
        }

        $data = json_decode($body === '' ? '{}' : $body, true);

        // An object decodes to an array too, so a list is told apart by its bracket.
        if (! is_array($data) || str_starts_with(ltrim($body), '[')) {
            return response()->json(['message' => 'El cuerpo debe ser un objeto JSON.'], 400);
        }

        $request->setJson(new InputBag($data));
        $request->request = $request->json();
        $request->attributes->set('robot_body', $body);

        return $next($request);
    }

    /**
     * The inflated body; stops as soon as it passes the limit (returning
     * limit + 1 bytes) and returns false when the gzip stream is broken.
     */
    private function inflate(string $compressed, int $limit): string|false
    {
        $context = inflate_init(ZLIB_ENCODING_GZIP);

        if ($context === false) {
            return false;
        }

        $inflated = '';

        foreach (str_split($compressed, self::CHUNK) as $chunk) {
            $piece = @inflate_add($context, $chunk, ZLIB_SYNC_FLUSH);

            if ($piece === false) {
                return false;
            }

            $inflated .= $piece;

            if (strlen($inflated) > $limit) {
                return substr($inflated, 0, $limit + 1);
            }
        }

        return inflate_get_status($context) === ZLIB_STREAM_END ? $inflated : false;
    }
}
