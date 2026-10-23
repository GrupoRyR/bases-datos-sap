<?php

use Laravel\Socialite\Facades\Socialite;
use SocialiteProviders\Microsoft\Provider as MicrosoftProvider;
use Tests\Modules\Core\Support\Environment;

/**
 * Sign-in settings of the Microsoft driver with $tenant as the tenant.
 */
function microsoftDriverConfig(?string $tenant): void
{
    config(['services.microsoft' => [
        'client_id' => 'client-id-de-prueba',
        'client_secret' => 'secreto-de-prueba',
        'redirect' => 'https://bases.example/auth/microsoft/callback',
        'tenant' => $tenant,
    ]]);
}

it('refuses to build the Microsoft driver without a tenant, instead of falling back to "common"', function (?string $tenant) {
    microsoftDriverConfig($tenant);

    expect(fn () => Socialite::driver('microsoft'))
        ->toThrow(RuntimeException::class, 'MICROSOFT_TENANT_ID is required');
})->with([
    'null' => [null],
    'empty' => [''],
    'spaces' => ['   '],
]);

it('builds the Microsoft driver for the configured tenant', function () {
    microsoftDriverConfig('00000000-0000-0000-0000-000000000000');

    $driver = Socialite::driver('microsoft');

    expect($driver)->toBeInstanceOf(MicrosoftProvider::class)
        ->and($driver->getLogoutUrl())
        ->toStartWith('https://login.microsoftonline.com/00000000-0000-0000-0000-000000000000/');
});

it('reads the Microsoft settings from MICROSOFT_* variables', function () {
    Environment::with([
        'MICROSOFT_CLIENT_ID' => 'client-id-de-prueba',
        'MICROSOFT_REDIRECT_URI' => 'https://bases.example/auth/microsoft/callback',
        'MICROSOFT_TENANT_ID' => '00000000-0000-0000-0000-000000000000',
    ], function () {
        $this->refreshApplication();

        expect(config('services.microsoft'))->toMatchArray([
            'client_id' => 'client-id-de-prueba',
            'redirect' => 'https://bases.example/auth/microsoft/callback',
            'tenant' => '00000000-0000-0000-0000-000000000000',
        ]);
    });
});

it('never has a client secret in tests, whatever the local .env says', function () {
    expect(config('services.microsoft.client_secret'))->toBeIn([null, '']);
});

it('still boots and answers the health check without a tenant', function () {
    Environment::with(['MICROSOFT_TENANT_ID' => ''], function () {
        $this->refreshApplication();

        expect(config('services.microsoft.tenant'))->toBeIn([null, '']);

        $this->get('/up')->assertOk();
    });
});
