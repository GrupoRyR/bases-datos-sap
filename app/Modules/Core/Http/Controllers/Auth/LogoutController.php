<?php

namespace App\Modules\Core\Http\Controllers\Auth;

use App\Modules\Core\Contracts\AuditLogger;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;

/**
 * POST /logout (core.logout, signed-in users only, CSRF-protected by the web
 * group): signs the user out of the app, forgets the session and goes back
 * to the sign-in page. The Microsoft session stays open: the next sign-in
 * may not ask for the password again.
 */
final class LogoutController
{
    public function __invoke(Request $request, AuditLogger $audit): RedirectResponse
    {
        // Before signing out, so the entry names the user as the actor.
        $audit->record('core.auth.signed_out', 'user', $request->user()?->getAuthIdentifier());

        Auth::logout();
        $request->session()->invalidate();
        $request->session()->regenerateToken();

        return redirect()->route('core.login')->with('status', __('core::ingreso.sesion_cerrada'));
    }
}
