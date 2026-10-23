<?php

use App\Models\User;
use Illuminate\Support\Facades\Route;

const DEACTIVATED_MESSAGE = 'Tu cuenta está desactivada. Si crees que es un error, habla con TI.';

beforeEach(function () {
    // A web page of no module and without the auth middleware: only the web
    // group stands between the user and the page.
    Route::middleware('web')->get('/_test/abierta', fn () => 'abierta');
});

it('signs an inactive user out of any web page and says why', function () {
    $this->actingAs(User::factory()->adminTi()->inactive()->create())
        ->get('/_test/abierta')
        ->assertRedirect('/login')
        ->assertSessionHas('error', DEACTIVATED_MESSAGE);

    $this->assertGuest();
});

it('answers 401 in JSON when an inactive user expects JSON', function () {
    $this->actingAs(User::factory()->consulta()->inactive()->create())
        ->getJson('/_test/abierta')
        ->assertUnauthorized()
        ->assertExactJson(['message' => DEACTIVATED_MESSAGE]);

    $this->assertGuest();
});

it('lets guests and active users through', function () {
    $this->get('/_test/abierta')->assertOk()->assertSee('abierta');

    $user = User::factory()->consulta()->create();

    $this->actingAs($user)->get('/_test/abierta')->assertOk()->assertSee('abierta');
    $this->assertAuthenticatedAs($user);
});

it('treats a user loaded without is_active as active instead of failing', function () {
    $id = User::factory()->consulta()->create()->getKey();

    $this->actingAs(User::query()->select(['id', 'name', 'email'])->findOrFail($id))
        ->get('/_test/abierta')
        ->assertOk();
});
