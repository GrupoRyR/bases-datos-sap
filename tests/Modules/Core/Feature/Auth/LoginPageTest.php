<?php

use App\Models\User;
use Illuminate\Support\Facades\Route;
use Tests\Modules\Core\Support\FakeIdentityProvider;

it('serves the sign-in routes of Core at the site root', function () {
    expect(route('core.login', absolute: false))->toBe('/login')
        ->and(route('core.auth.redirect', absolute: false))->toBe('/auth/microsoft')
        ->and(route('core.auth.callback', absolute: false))->toBe('/auth/microsoft/callback')
        ->and(route('core.inicio', absolute: false))->toBe('/')
        ->and(route('core.sin-acceso', absolute: false))->toBe('/sin-acceso')
        ->and(Route::getRoutes()->getByName('core.login')?->gatherMiddleware())->toContain('web', 'guest');
});

it('sends guests to the sign-in page', function (string $page) {
    $this->get($page)->assertRedirect('/login');
})->with(['home' => ['/'], 'no access' => ['/sin-acceso']]);

it('shows the sign-in page with the Microsoft button', function () {
    $this->get('/login')
        ->assertOk()
        ->assertViewIs('core::auth.login')
        ->assertSee('Entrar con Microsoft')
        ->assertSee(route('core.auth.redirect'), false);
});

it('shows the error of a failed sign-in', function () {
    $this->withSession(['error' => 'No pudimos completar el ingreso con Microsoft. Inténtalo de nuevo.'])
        ->get('/login')
        ->assertOk()
        ->assertSee('No pudimos completar el ingreso con Microsoft. Inténtalo de nuevo.');
});

it('sends the guest to the Microsoft sign-in page of the tenant', function () {
    FakeIdentityProvider::install($this->app);

    $this->get('/auth/microsoft')->assertRedirect(FakeIdentityProvider::AUTHORIZE_URL);
});

it('sends signed-in users home from the sign-in pages', function (string $page) {
    $this->actingAs(User::factory()->consulta()->create())->get($page)->assertRedirect('/');
})->with(['sign-in page' => ['/login'], 'Microsoft redirect' => ['/auth/microsoft']]);
