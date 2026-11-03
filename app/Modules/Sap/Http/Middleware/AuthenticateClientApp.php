<?php

namespace App\Modules\Sap\Http\Middleware;

use App\Modules\Sap\Application\Apps\AppKeys;
use Closure;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\RateLimiter;
use Symfony\Component\HttpFoundation\Response;

/**
 * Lets an app through with its key in "Authorization: Bearer <key>"
 * (docs/contrato-robot.md, section 7.4). A missing, unknown or revoked key
 * gets 401. The app is in the "client_app" request attribute.
 *
 * Every 401 counts against the IP. The "sap-apps" limit goes by key, so a
 * client trying random keys would get a fresh bucket each time; past
 * sap.apps.failed_auth_per_minute failures the IP gets 429 before any key
 * is looked up. A good key never counts.
 */
final class AuthenticateClientApp
{
    private const DECAY_SECONDS = 60;

    public function __construct(private readonly AppKeys $keys) {}

    public function handle(Request $request, Closure $next): Response
    {
        $failures = 'sap-apps-fail|'.$request->ip();

        if (RateLimiter::tooManyAttempts($failures, (int) config('sap.apps.failed_auth_per_minute'))) {
            return response()->json(['message' => 'Demasiados intentos con una llave inválida.'], 429, [
                'Retry-After' => RateLimiter::availableIn($failures),
            ]);
        }

        $key = (string) $request->bearerToken();
        $app = $key === '' ? null : $this->keys->find($key);

        if ($app === null) {
            RateLimiter::hit($failures, self::DECAY_SECONDS);

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
