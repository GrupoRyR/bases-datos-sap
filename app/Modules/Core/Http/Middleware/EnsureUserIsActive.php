<?php

namespace App\Modules\Core\Http\Middleware;

use App\Models\User;
use Closure;
use Illuminate\Contracts\Auth\Factory as AuthFactory;
use Illuminate\Contracts\Auth\StatefulGuard;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/**
 * Signs out a deactivated user on their next request. CoreServiceProvider
 * appends it to the "web" group, so it guards every web page, with or
 * without the auth middleware.
 */
final class EnsureUserIsActive
{
    public function __construct(private readonly AuthFactory $auth) {}

    /**
     * @param  Closure(Request): Response  $next
     */
    public function handle(Request $request, Closure $next): Response
    {
        $guard = $this->auth->guard('web');
        $user = $guard->user();

        if (! $guard instanceof StatefulGuard || ! $user instanceof User || self::isActive($user)) {
            return $next($request);
        }

        $guard->logout();

        if ($request->hasSession()) {
            $request->session()->invalidate();
            $request->session()->regenerateToken();
        }

        $message = __('core::ingreso.cuenta_desactivada');

        if ($request->expectsJson()) {
            return response()->json(['message' => $message], Response::HTTP_UNAUTHORIZED);
        }

        return redirect('/login')->with('error', $message);
    }

    /**
     * Reads the raw attribute: a user loaded without the column may lack
     * is_active, which then counts as the column default (active).
     */
    private static function isActive(User $user): bool
    {
        return (bool) ($user->getAttributes()['is_active'] ?? true);
    }
}
