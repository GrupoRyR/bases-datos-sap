<?php

use App\Models\User;
use Illuminate\Http\Middleware\TrustProxies;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Route;
use Illuminate\Testing\TestResponse;
use Symfony\Component\HttpFoundation\Response;
use Tests\TestCase;

/*
| Core's routes/web.php registers the demo sign-in only when the application
| boots in local. Tests boot in "testing", so each test switches the
| environment and loads Core's routes again, as its provider does on boot.
| Outside "testing" the CSRF check is on, so the sign-in posts the session
| token like the form does.
*/
function bootCoreRoutesIn(string $environment): void
{
    app()['env'] = $environment;

    Route::middleware('web')->name('core.')->group(base_path('app/Modules/Core/routes/web.php'));
    app('router')->getRoutes()->refreshNameLookups();
}

/**
 * @return TestResponse<Response>
 */
function postDemoSignIn(TestCase $test, string $uri, string $address = '127.0.0.1'): TestResponse
{
    return $test->withServerVariables(['REMOTE_ADDR' => $address])
        ->withSession(['_token' => 'demo-csrf-token'])
        ->post($uri, ['_token' => 'demo-csrf-token']);
}

it('does not register the demo sign-in in the testing environment', function () {
    $user = User::factory()->adminTi()->create();

    expect(Route::has('core.dev.entrar'))->toBeFalse()
        ->and(Route::has('core.dev.entrar.usuario'))->toBeFalse();

    $this->get('/dev/entrar')->assertNotFound();
    postDemoSignIn($this, "/dev/entrar/{$user->id}")->assertNotFound();
    $this->assertGuest();
});

it('does not register the demo sign-in in production', function () {
    $user = User::factory()->adminTi()->create();

    bootCoreRoutesIn('production');

    expect(Route::has('core.dev.entrar'))->toBeFalse()
        ->and(Route::has('core.dev.entrar.usuario'))->toBeFalse();

    $this->get('/dev/entrar')->assertNotFound();
    postDemoSignIn($this, "/dev/entrar/{$user->id}")->assertNotFound();
    $this->assertGuest();
});

it('serves the demo sign-in in local at /dev/entrar, the sign-in as a POST in the web group', function () {
    bootCoreRoutesIn('local');

    $route = Route::getRoutes()->getByName('core.dev.entrar.usuario');

    expect(route('core.dev.entrar', absolute: false))->toBe('/dev/entrar')
        ->and($route)->not->toBeNull()
        ->and($route?->methods())->toBe(['POST'])
        ->and($route?->gatherMiddleware())->toContain('web');
});

it('answers 404 in local to a request that does not come from this machine', function () {
    $user = User::factory()->adminTi()->create();

    bootCoreRoutesIn('local');

    $this->withServerVariables(['REMOTE_ADDR' => '10.0.0.8'])->get(route('core.dev.entrar'))->assertNotFound();
    postDemoSignIn($this, route('core.dev.entrar.usuario', $user), '10.0.0.8')->assertNotFound();
    $this->assertGuest();
});

it('ignores forwarded headers that claim the request is local', function () {
    $user = User::factory()->adminTi()->create();

    bootCoreRoutesIn('local');

    $this->withHeader('X-Forwarded-For', '127.0.0.1');

    postDemoSignIn($this, route('core.dev.entrar.usuario', $user), '10.0.0.8')->assertNotFound();
    $this->assertGuest();
});

it('ignores forwarded headers even when every proxy is trusted', function () {
    $user = User::factory()->adminTi()->create();

    bootCoreRoutesIn('local');
    TrustProxies::at('*');

    try {
        $this->withHeader('X-Forwarded-For', '127.0.0.1');

        postDemoSignIn($this, route('core.dev.entrar.usuario', $user), '10.0.0.8')->assertNotFound();
        $this->assertGuest();
    } finally {
        TrustProxies::flushState();
    }
});

it('answers 404 if the routes were cached in local but the app now runs elsewhere', function () {
    $user = User::factory()->adminTi()->create();

    bootCoreRoutesIn('local');
    app()['env'] = 'production';

    $this->get(route('core.dev.entrar'))->assertNotFound();
    postDemoSignIn($this, route('core.dev.entrar.usuario', $user))->assertNotFound();
    $this->assertGuest();
});

it('lists the active users with a role', function (string $address) {
    $admin = User::factory()->adminTi()->create(['name' => 'Admin TI de prueba']);
    User::factory()->consulta()->create(['name' => 'Consulta de prueba']);
    User::factory()->create(['name' => 'Sin Rol']);
    User::factory()->adminTi()->inactive()->create(['name' => 'Inactivo Persona']);

    bootCoreRoutesIn('local');

    $this->withServerVariables(['REMOTE_ADDR' => $address])
        ->get(route('core.dev.entrar'))
        ->assertOk()
        ->assertSee('Entra como un usuario de prueba')
        ->assertSee('Admin TI de prueba')
        ->assertSee($admin->email)
        ->assertSee('Consulta de prueba')
        ->assertSee(route('core.dev.entrar.usuario', $admin), false)
        ->assertSee('name="_token"', false)
        ->assertDontSee('Sin Rol')
        ->assertDontSee('Inactivo Persona');

    $this->assertGuest();
})->with(['IPv4' => '127.0.0.1', 'IPv6' => '::1']);

it('says how to create the demo users when there are none', function () {
    bootCoreRoutesIn('local');

    $this->get(route('core.dev.entrar'))->assertOk()->assertSee('php artisan migrate --seed');
});

it('signs in as the chosen user, sends them home and audits it as a demo', function (string $address) {
    $reader = User::factory()->consulta()->create();

    bootCoreRoutesIn('local');

    postDemoSignIn($this, route('core.dev.entrar.usuario', $reader), $address)
        ->assertRedirect(route('core.inicio'));

    $this->assertAuthenticatedAs($reader);

    $entry = DB::table('audit_logs')->sole();

    expect($entry->action)->toBe('core.auth.signed_in')
        ->and($entry->subject_id)->toBe((string) $reader->id)
        ->and((int) $entry->user_id)->toBe($reader->id)
        ->and(json_decode((string) $entry->context, true))->toBe(['method' => 'demo']);
})->with(['IPv4' => '127.0.0.1', 'IPv6' => '::1']);

it('refuses a sign-in without the CSRF token of the session', function () {
    $admin = User::factory()->adminTi()->create();

    bootCoreRoutesIn('local');

    $this->post(route('core.dev.entrar.usuario', $admin))->assertStatus(419);
    $this->assertGuest();
});

it('does not sign in with a GET on the sign-in URL', function () {
    $admin = User::factory()->adminTi()->create();

    bootCoreRoutesIn('local');

    $this->get(route('core.dev.entrar.usuario', $admin))->assertMethodNotAllowed();
    $this->assertGuest();
});

it('refuses inactive users, users without a role and unknown users', function () {
    $inactive = User::factory()->adminTi()->inactive()->create();
    $withoutRole = User::factory()->create();

    bootCoreRoutesIn('local');

    postDemoSignIn($this, route('core.dev.entrar.usuario', $inactive))->assertNotFound();
    postDemoSignIn($this, route('core.dev.entrar.usuario', $withoutRole))->assertNotFound();
    postDemoSignIn($this, '/dev/entrar/999999')->assertNotFound();
    $this->assertGuest();

    expect(DB::table('audit_logs')->count())->toBe(0);
});
