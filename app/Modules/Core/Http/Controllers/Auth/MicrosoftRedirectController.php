<?php

namespace App\Modules\Core\Http\Controllers\Auth;

use App\Modules\Core\Application\Auth\IdentityProvider;
use Symfony\Component\HttpFoundation\RedirectResponse;

/**
 * GET /auth/microsoft (core.auth.redirect, guests only): sends the guest to
 * the Microsoft sign-in page of the configured tenant.
 */
final class MicrosoftRedirectController
{
    public function __invoke(IdentityProvider $microsoft): RedirectResponse
    {
        return $microsoft->redirect();
    }
}
