<?php

use App\Modules\Core\Application\Auth\IdentityProvider;
use App\Modules\Core\Application\Auth\MicrosoftIdentity;
use App\Modules\Core\Infrastructure\Auth\SocialiteMicrosoftIdentityProvider;
use Laravel\Socialite\Facades\Socialite;
use SocialiteProviders\Microsoft\MicrosoftUser;
use SocialiteProviders\Microsoft\Provider as MicrosoftProvider;

/**
 * The Graph /me profile of Ana, with $overrides.
 *
 * @param  array<string, string|null>  $overrides
 * @return array<string, string|null>
 */
function graphProfile(array $overrides = []): array
{
    return array_merge([
        'id' => 'oid-ana',
        'displayName' => 'Ana Gómez',
        'mail' => 'Ana.Gomez@Segurex.com',
        'userPrincipalName' => 'agomez@segurexlatam.onmicrosoft.com',
    ], $overrides);
}

describe('MicrosoftIdentity', function () {
    it('takes the object id, the tenant, the normalized mail and the display name', function () {
        $identity = MicrosoftIdentity::fromGraph(graphProfile(['mail' => ' Ana.Gomez@Segurex.com ']), 'tenant-ryr');

        expect($identity->objectId)->toBe('oid-ana')
            ->and($identity->tenantId)->toBe('tenant-ryr')
            ->and($identity->email)->toBe('ana.gomez@segurex.com')
            ->and($identity->name)->toBe('Ana Gómez');
    });

    it('falls back to the user principal name without a mailbox', function (?string $mail) {
        expect(MicrosoftIdentity::fromGraph(graphProfile(['mail' => $mail]), 'tenant-ryr')->email)
            ->toBe('agomez@segurexlatam.onmicrosoft.com');
    })->with(['null' => [null], 'empty' => ['']]);

    it('falls back to the e-mail without a display name', function (?string $name) {
        expect(MicrosoftIdentity::fromGraph(graphProfile(['displayName' => $name]), null)->name)
            ->toBe('ana.gomez@segurex.com');
    })->with(['null' => [null], 'blank' => ['  ']]);

    it('refuses a profile without an object id or an e-mail', function (array $overrides) {
        expect(fn () => MicrosoftIdentity::fromGraph(graphProfile($overrides), 'tenant-ryr'))
            ->toThrow(UnexpectedValueException::class);
    })->with([
        'no object id' => [['id' => null]],
        'no e-mail' => [['mail' => null, 'userPrincipalName' => null]],
    ]);
});

describe('SocialiteMicrosoftIdentityProvider', function () {
    it('is the IdentityProvider of the container', function () {
        expect(app(IdentityProvider::class))->toBeInstanceOf(SocialiteMicrosoftIdentityProvider::class);
    });

    it('reads the profile and the tenant of the validated id token', function (?object $claims, ?string $tenant) {
        $driver = Mockery::mock(MicrosoftProvider::class);
        $driver->shouldReceive('user')->once()->andReturn((new MicrosoftUser)->setRaw(graphProfile()));
        $driver->shouldReceive('getClaims')->andReturn($claims);
        Socialite::shouldReceive('driver')->with('microsoft')->andReturn($driver);

        $identity = app(SocialiteMicrosoftIdentityProvider::class)->user();

        expect($identity->objectId)->toBe('oid-ana')
            ->and($identity->email)->toBe('ana.gomez@segurex.com')
            ->and($identity->tenantId)->toBe($tenant);
    })->with([
        'tid claim' => [(object) ['tid' => 'tenant-ryr', 'oid' => 'oid-ana'], 'tenant-ryr'],
        'no tid claim' => [(object) ['oid' => 'oid-ana'], null],
        'empty tid claim' => [(object) ['tid' => ''], null],
        'no id token' => [null, null],
    ]);

    it('redirects to the sign-in page of the configured tenant, without calling Microsoft', function () {
        config(['services.microsoft' => [
            'client_id' => 'client-id-de-prueba',
            'client_secret' => 'secreto-de-prueba',
            'redirect' => 'https://bases.example/auth/microsoft/callback',
            'tenant' => 'tenant-ryr',
        ]]);
        // The driver keeps the OAuth state in the session of the request.
        request()->setLaravelSession(app('session')->driver());

        $location = app(SocialiteMicrosoftIdentityProvider::class)->redirect()->getTargetUrl();
        parse_str((string) parse_url($location, PHP_URL_QUERY), $query);

        expect($location)->toStartWith('https://login.microsoftonline.com/tenant-ryr/oauth2/v2.0/authorize?')
            ->and($query)->toMatchArray([
                'client_id' => 'client-id-de-prueba',
                'redirect_uri' => 'https://bases.example/auth/microsoft/callback',
                'response_type' => 'code',
                'scope' => 'openid profile User.Read',
            ])
            ->and($query['state'] ?? null)->not->toBeEmpty()->toBe(session('state'));
    });
});
