<?php

use App\Models\User;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Route;

it('is served at POST /logout, behind the session, CSRF and auth middleware', function () {
    $route = Route::getRoutes()->getByName('core.logout');

    expect(route('core.logout', absolute: false))->toBe('/logout')
        ->and($route?->methods())->toBe(['POST'])
        ->and($route?->gatherMiddleware())->toContain('web', 'auth');
});

it('signs the user out, forgets the session and audits it', function () {
    $user = User::factory()->consulta()->create();

    $this->actingAs($user)
        ->withSession(['algo' => 'valor', '_token' => 'token-anterior'])
        ->post('/logout')
        ->assertRedirect('/login')
        ->assertSessionHas('status', 'Cerraste sesión.')
        ->assertSessionMissing('algo');

    $this->assertGuest();

    $entry = DB::table('audit_logs')->sole();

    expect(session()->token())->not->toBe('token-anterior')
        ->and($entry->action)->toBe('core.auth.signed_out')
        ->and($entry->subject_type)->toBe('user')
        ->and($entry->subject_id)->toBe((string) $user->id)
        ->and((int) $entry->user_id)->toBe($user->id);
});

it('says goodbye on the sign-in page', function () {
    $this->actingAs(User::factory()->create())
        ->followingRedirects()
        ->post('/logout')
        ->assertOk()
        ->assertViewIs('core::auth.login')
        ->assertSee('Cerraste sesión.');
});

it('sends guests to the sign-in page without auditing', function () {
    $this->post('/logout')->assertRedirect('/login');

    expect(DB::table('audit_logs')->count())->toBe(0);
});

it('does not sign out through a link', function () {
    $this->actingAs(User::factory()->create())->get('/logout')->assertMethodNotAllowed();

    $this->assertAuthenticated();
});
