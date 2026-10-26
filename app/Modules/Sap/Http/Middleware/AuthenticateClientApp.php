<?php

namespace App\Modules\Sap\Http\Middleware;

use App\Modules\Sap\Application\Apps\AppKeys;
use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/**
 * Lets an app through with its key in "Authorization: Bearer <key>"
 * (docs/contrato-robot.md, section 7.4). A missing, unknown or revoked key
 * gets 401. The app is in the "client_app" request attribute.
 */
final class AuthenticateClientApp
{
    public function __construct(private readonly AppKeys $keys) {}

    public function handle(Request $request, Closure $next): Response
    {
        $key = (string) $request->bearerToken();
        $app = $key === '' ? null : $this->keys->find($key);

        if ($app === null) {
            return response()->json(['message' => 'Llave inválida.'], 401);
        }

        // At most one write per minute per app.
        if ($app->last_used_at === null || $app->last_used_at->lt(now()->subMinute())) {
            $app->forceFill(['last_used_at' => now()])->save();
        }

        $request->attributes->set('client_app', $app);

        return $next($request);
    }
}
