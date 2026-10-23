<?php

namespace App\Modules\Core\Application\Auth;

use Symfony\Component\HttpFoundation\RedirectResponse;
use Throwable;

/**
 * The Microsoft Entra ID sign-in (OAuth 2.0 / OpenID Connect), seen from
 * Core. Infrastructure\Auth\SocialiteMicrosoftIdentityProvider implements it;
 * tests bind a fake, so they never reach Microsoft.
 */
interface IdentityProvider
{
    /**
     * The redirect to the Microsoft sign-in page of the configured tenant.
     */
    public function redirect(): RedirectResponse;

    /**
     * The identity Microsoft sent back to the callback.
     *
     * @throws Throwable When the response cannot be trusted or read: invalid
     *                   state, a failed token or Graph request, an invalid id
     *                   token or a profile without object id or e-mail.
     */
    public function user(): MicrosoftIdentity;
}
