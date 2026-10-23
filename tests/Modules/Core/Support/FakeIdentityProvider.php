<?php

namespace Tests\Modules\Core\Support;

use App\Modules\Core\Application\Auth\IdentityProvider;
use App\Modules\Core\Application\Auth\MicrosoftIdentity;
use Illuminate\Contracts\Container\Container;
use LogicException;
use Symfony\Component\HttpFoundation\RedirectResponse;
use Throwable;

/**
 * Stands in for Microsoft Entra ID, so tests never reach Microsoft. Install
 * it, then tell it what the next callback gets: signsIn() an identity or
 * fails() with an exception.
 */
final class FakeIdentityProvider implements IdentityProvider
{
    /**
     * The tenant tests configure in services.microsoft.tenant.
     */
    public const string TENANT = '11111111-2222-3333-4444-555555555555';

    public const string AUTHORIZE_URL = 'https://login.microsoftonline.com/11111111-2222-3333-4444-555555555555/oauth2/v2.0/authorize?fake=1';

    private MicrosoftIdentity|Throwable|null $outcome = null;

    /**
     * Binds a new fake as the IdentityProvider of $app.
     */
    public static function install(Container $app): self
    {
        $fake = new self;
        $app->instance(IdentityProvider::class, $fake);

        return $fake;
    }

    /**
     * An identity of the configured tenant, unless $tenantId says otherwise.
     */
    public static function identity(
        string $email = 'ana.gomez@segurex.com',
        string $objectId = 'oid-ana',
        ?string $tenantId = self::TENANT,
        ?string $name = 'Ana Gómez',
    ): MicrosoftIdentity {
        return new MicrosoftIdentity($objectId, $tenantId, $email, $name);
    }

    public function signsIn(MicrosoftIdentity $identity): self
    {
        $this->outcome = $identity;

        return $this;
    }

    public function fails(Throwable $exception): self
    {
        $this->outcome = $exception;

        return $this;
    }

    public function redirect(): RedirectResponse
    {
        return new RedirectResponse(self::AUTHORIZE_URL);
    }

    public function user(): MicrosoftIdentity
    {
        if ($this->outcome instanceof Throwable) {
            throw $this->outcome;
        }

        return $this->outcome ?? throw new LogicException('Tell the fake who signs in with signsIn() or fails() first.');
    }
}
