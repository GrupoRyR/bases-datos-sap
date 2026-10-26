<?php

namespace App\Modules\Sap\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/**
 * Answers 413 to a body over the limit as it travels, before the signature
 * is checked (docs/contrato-robot.md, section 2).
 */
final class LimitRobotPayload
{
    public function handle(Request $request, Closure $next): Response
    {
        $limit = (int) config('sap.robot.max_body_bytes');
        $declared = $request->headers->get('Content-Length');

        if ((is_numeric($declared) && (int) $declared > $limit) || strlen($request->getContent()) > $limit) {
            return response()->json(['message' => 'El cuerpo es demasiado grande.'], 413);
        }

        return $next($request);
    }
}
