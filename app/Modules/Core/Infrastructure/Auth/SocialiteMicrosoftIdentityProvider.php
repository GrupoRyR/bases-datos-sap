<?php

namespace App\Modules\Core\Infrastructure\Auth;

use App\Modules\Core\Application\Auth\IdentityProvider;
use App\Modules\Core\Application\Auth\MicrosoftIdentity;
use Laravel\Socialite\Contracts\Factory as Socialite;
use LogicException;
use SocialiteProviders\Microsoft\Provider as MicrosoftProvider;
use Symfony\Component\HttpFoundation\RedirectResponse;

/**
 * IdentityProvider over the "microsoft" Socialite driver, which
 * CoreServiceProvider registers for the configured tenant only (it refuses
 * to build without one). The driver checks the OAuth state, trades the code
 * for the tokens, validates the id token against the tenant's keys and reads
 * the Graph /me profile (scopes openid, profile and User.Read). The optional
 * "acct" claim of the id token marks a guest (B2B) account.
 */
final class SocialiteMicrosoftIdentityProvider implements IdentityProvider
{
    public function __construct(private readonly Socialite $socialite) {}

    public function redirect(): RedirectResponse
    {
        return $this->driver()->redirect();
    }

    public function user(): MicrosoftIdentity
    {
        $driver = $this->driver();
        // First: it fills the token response the claims are read from.
        $profile = $driver->user()->getRaw();
        $claims = $driver->getClaims();
        $tenantId = $claims->tid ?? null;
        // Optional claim: 1 for a guest, 0 for a member.
        $account = $claims->acct ?? null;

        return MicrosoftIdentity::fromGraph(
            $profile,
            is_string($tenantId) && $tenantId !== '' ? $tenantId : null,
            in_array($account, [1, '1'], true),
        );
    }

    private function driver(): MicrosoftProvider
    {
        $driver = $this->socialite->driver('microsoft');

        if (! $driver instanceof MicrosoftProvider) {
            throw new LogicException('The "microsoft" Socialite driver must be the SocialiteProviders Microsoft provider.');
        }

        return $driver;
    }
}
