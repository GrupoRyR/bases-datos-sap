<?php

namespace App\Modules\Core\Http\Controllers\Auth;

use App\Modules\Core\Application\Auth\IdentityProvider;
use App\Modules\Core\Application\Auth\SignInRejected;
use App\Modules\Core\Application\Auth\SignInWithMicrosoft;
use App\Modules\Core\Contracts\AuditLogger;
use Exception;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;

/**
 * GET /auth/microsoft/callback (core.auth.callback, guests only): where
 * Microsoft returns the guest. It must match MICROSOFT_REDIRECT_URI.
 *
 * A failure of Microsoft (invalid state, a failed request, an invalid id
 * token) is reported and the guest may try again; a rejected account goes
 * back to the sign-in page with one message, whatever the reason. A user who
 * signs in starts a new session and goes to the page they asked for, or home.
 */
final class MicrosoftCallbackController
{
    public function __invoke(
        Request $request,
        IdentityProvider $microsoft,
        SignInWithMicrosoft $signIn,
        AuditLogger $audit,
    ): RedirectResponse {
        try {
            $identity = $microsoft->user();
        } catch (Exception $exception) {
            report($exception);

            return redirect()->route('core.login')->with('error', __('core::ingreso.error'));
        }

        try {
            $user = $signIn->handle($identity);
        } catch (SignInRejected) {
            return redirect()->route('core.login')->with('error', __('core::ingreso.rechazado'));
        }

        Auth::login($user);
        $request->session()->regenerate();

        $audit->record('core.auth.signed_in', 'user', $user->id, ['method' => 'microsoft']);

        return redirect()->intended(route('core.inicio'));
    }
}
