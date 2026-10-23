<?php

use App\Models\User;

it('greets a user with a role and shows their role and the sign-out button', function (string $state, string $label) {
    $user = User::factory()->{$state}()->create(['name' => 'Ana Gómez']);

    $this->actingAs($user)
        ->get('/')
        ->assertOk()
        ->assertViewIs('core::inicio')
        ->assertSee('Hola, Ana Gómez')
        ->assertSee($label)
        ->assertSee('Cerrar sesión')
        ->assertSee(route('core.logout'), false)
        ->assertSee('name="_token"', false);
})->with([
    'admin TI' => ['adminTi', 'Admin TI'],
    'consulta' => ['consulta', 'Consulta'],
]);

it('sends a user without a role to the page that asks for access', function () {
    $this->actingAs(User::factory()->create())->get('/')->assertRedirect('/sin-acceso');
});

it('tells a user without a role to ask TI, and lets them sign out', function () {
    $this->actingAs(User::factory()->create(['email' => 'ana.gomez@segurex.com']))
        ->get('/sin-acceso')
        ->assertOk()
        ->assertViewIs('core::sin-acceso')
        ->assertSee('Todavía no tienes acceso')
        ->assertSee('ana.gomez@segurex.com')
        ->assertSee('TI')
        ->assertSee('Cerrar sesión');
});

it('sends a user with a role home from the no-access page', function () {
    $this->actingAs(User::factory()->consulta()->create())->get('/sin-acceso')->assertRedirect('/');
});

it('serves the sign-in page instead of the default welcome page', function () {
    $this->get('/')->assertRedirect('/login');

    expect(view()->exists('welcome'))->toBeFalse();
});
