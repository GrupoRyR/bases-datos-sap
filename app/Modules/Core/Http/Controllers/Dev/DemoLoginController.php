<?php

namespace App\Modules\Core\Http\Controllers\Dev;

use App\Models\User;
use App\Modules\Core\Contracts\AuditLogger;
use Illuminate\Contracts\View\View;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;

/**
 * GET /dev/entrar (core.dev.entrar) and POST /dev/entrar/{user}
 * (core.dev.entrar.usuario): sign in as a demo user without Microsoft, only
 * on a developer's machine, to walk the panel with CoreDemoSeeder's users.
 *
 * Three locks keep it away from any real server: Core's routes/web.php
 * registers the routes only in local; this controller answers 404 outside
 * local (a route cache built in local) and to any request whose socket
 * address is not the loopback (REMOTE_ADDR, never a forwarded header); and
 * signing in is a POST checked by the CSRF middleware of the web group.
 */
final class DemoLoginController
{
    private const array LOOPBACK = ['127.0.0.1', '::1'];

    public function index(Request $request): View
    {
        self::ensureLocalRequest($request);

        $users = User::query()
            ->where('is_active', true)
            ->whereNotNull('role')
            ->orderBy('name')
            ->get();

        return view('core::dev.entrar', ['users' => $users]);
    }

    public function store(Request $request, User $user, AuditLogger $audit): RedirectResponse
    {
        self::ensureLocalRequest($request);

        abort_unless($user->is_active && $user->role !== null, 404);

        // A clean session (invalidate also renews its id): nothing of the
        // previous demo user (intended URL) carries over.
        $request->session()->invalidate();
        Auth::login($user);

        // The same entry as a Microsoft sign-in, so the audit log reads alike.
        $audit->record('core.auth.signed_in', 'user', $user->id, ['method' => 'demo']);

        return redirect()->route('core.inicio');
    }

    private static function ensureLocalRequest(Request $request): void
    {
        abort_unless(app()->isLocal(), 404);
        abort_unless(in_array($request->server('REMOTE_ADDR'), self::LOOPBACK, true), 404);
    }
}
