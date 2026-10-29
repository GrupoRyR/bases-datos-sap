<?php

use App\Models\User;
use App\Modules\Sap\Contracts\ClientAppKeys;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use Tests\Modules\Panel\Support\FakeClientAppKeys;

beforeEach(function () {
    $this->travelTo(CarbonImmutable::parse('2026-10-29 11:00', 'America/Bogota'));

    $this->keys = new FakeClientAppKeys;
    $this->app->instance(ClientAppKeys::class, $this->keys);

    $this->admin = User::factory()->adminTi()->create();
});

it('sends a guest to the sign-in page', function () {
    $this->get('/panel/apps')->assertRedirect('/login');
    $this->post('/panel/apps', ['nombre' => 'Portal RYR'])->assertRedirect('/login');
    $this->post('/panel/apps/1/llave')->assertRedirect('/login');
    $this->post('/panel/apps/1/revocar')->assertRedirect('/login');
});

it('forbids consulta and users without a role on every route', function (?string $role) {
    $app = $this->keys->add('Portal RYR');
    $user = $role === null ? User::factory()->create() : User::factory()->{$role}()->create();

    $this->actingAs($user)->get('/panel/apps')->assertForbidden();
    $this->actingAs($user)->post('/panel/apps', ['nombre' => 'Cotizador'])->assertForbidden();
    $this->actingAs($user)->post("/panel/apps/{$app->id}/llave")->assertForbidden();
    $this->actingAs($user)->post("/panel/apps/{$app->id}/revocar")->assertForbidden();

    expect($this->keys->calls)->toBe([])
        ->and(DB::table('audit_logs')->count())->toBe(0);
})->with(['consulta' => 'consulta', 'no role' => null]);

it('lists every app with its state, key prefix and dates, never a full key', function () {
    $active = $this->keys->add('Portal RYR', createdAt: '2026-10-01 08:00', lastUsedAt: '2026-10-28 23:10');
    $this->keys->add('Cotizador', createdAt: '2026-10-05 09:30');
    $revoked = $this->keys->add('App vieja', createdAt: '2026-10-02 07:00', revokedAt: '2026-10-20 16:45');

    $response = $this->actingAs($this->admin)
        ->get(route('panel.apps'))
        ->assertOk()
        ->assertViewIs('panel::apps')
        ->assertSee('Apps conectadas')
        ->assertSee('Cada app pide actualizaciones con su propia llave. La llave se muestra una sola vez.')
        ->assertSee('Nombre de la app')
        ->assertSee('Crear app y llave')
        ->assertSeeInOrder(['App vieja', 'Revocada', 'Revocada el 20 oct a las 16:45', 'Llave '.$revoked->keyPrefix.'…', 'Creada el 2 oct a las 07:00', 'Nunca la ha usado', 'Reactivar con llave nueva'])
        ->assertSeeInOrder(['Cotizador', 'Activa', 'Creada el 5 oct a las 09:30', 'Nunca la ha usado', 'Generar llave nueva', 'La llave actual deja de servir en ese momento.'])
        ->assertSeeInOrder(['Portal RYR', 'Activa', 'Llave '.$active->keyPrefix.'…', 'Creada el 1 oct a las 08:00', 'Último uso el 28 oct a las 23:10', 'Revocar', '¿Revocar la llave de Portal RYR? La app deja de poder pedir actualizaciones.', 'Sí, revocar'])
        ->assertSee('action="'.route('panel.apps.rotate', $active->id).'"', false)
        ->assertSee('action="'.route('panel.apps.revoke', $active->id).'"', false)
        ->assertDontSee('action="'.route('panel.apps.revoke', $revoked->id).'"', false)
        ->assertDontSee('s3cr3t');

    expect(substr_count($response->getContent(), 'Sí, revocar'))->toBe(2);
});

it('says when there are no apps yet', function () {
    $this->actingAs($this->admin)
        ->get('/panel/apps')
        ->assertOk()
        ->assertSee('Aún no hay apps conectadas.');
});

it('creates an app and shows its key once, not to be stored', function () {
    $response = $this->actingAs($this->admin)
        ->post('/panel/apps', ['nombre' => '  Portal RYR  '])
        ->assertOk()
        ->assertViewIs('panel::apps-llave')
        ->assertSee('Llave de Portal RYR')
        ->assertSee('Copia la llave ahora')
        ->assertSee('No se vuelve a mostrar. Si la pierdes, genera una nueva.')
        ->assertSee('Volver a las apps')
        ->assertSee(route('panel.apps'), false);

    $key = $this->keys->keys[0];

    expect($this->keys->calls)->toBe([['method' => 'issue', 'argument' => 'Portal RYR']])
        ->and($response->getContent())->toMatch('/<input[^>]*value="'.preg_quote($key, '/').'"[^>]*readonly/')
        ->and($response->headers->get('Cache-Control'))->toContain('no-store')
        ->and(json_encode(session()->all()))->not->toContain($key);

    $this->actingAs($this->admin)->get('/panel/apps')->assertSee('Portal RYR')->assertDontSee($key);
});

it('audits the new app with its name and prefix, never the key', function () {
    $this->actingAs($this->admin)->post('/panel/apps', ['nombre' => 'Portal RYR']);

    $row = DB::table('audit_logs')->sole();
    $app = $this->keys->all()[0];

    expect($row->action)->toBe('panel.app.created')
        ->and($row->subject_type)->toBe('app')
        ->and($row->subject_id)->toBe((string) $app->id)
        ->and((int) $row->user_id)->toBe($this->admin->id)
        ->and(json_decode((string) $row->context, true))->toEqual(['nombre' => 'Portal RYR', 'prefijo' => $app->keyPrefix])
        ->and((string) $row->context)->not->toContain($this->keys->keys[0]);
});

it('refuses an empty, long or taken name on the list page, keeping it, without auditing', function (string $name, string $message) {
    $this->keys->add('Portal RYR', revokedAt: '2026-10-20 16:45');

    $this->actingAs($this->admin)
        ->followingRedirects()
        ->from('/panel/apps')
        ->post('/panel/apps', ['nombre' => $name])
        ->assertOk()
        ->assertViewIs('panel::apps')
        ->assertSee($message)
        ->assertSee('aria-describedby="error-nombre"', false)
        ->assertSee('value="'.e(trim($name)).'"', false);

    expect(DB::table('audit_logs')->count())->toBe(0)
        ->and($this->keys->keys)->toHaveCount(1);
})->with([
    'taken, even by a revoked app' => ['Portal RYR', 'Ya hay una app con ese nombre.'],
    'empty' => ['   ', 'Escribe el nombre de la app.'],
    'too long' => [str_repeat('a', 101), 'Escribe máximo 100 caracteres.'],
]);

it('rotates the key of an app and shows the new one once', function (?string $revokedAt, string $button) {
    $app = $this->keys->add('Portal RYR', revokedAt: $revokedAt);

    $this->actingAs($this->admin)->get('/panel/apps')->assertSee($button);

    $response = $this->actingAs($this->admin)
        ->post(route('panel.apps.rotate', $app->id))
        ->assertOk()
        ->assertViewIs('panel::apps-llave')
        ->assertSee('Llave de Portal RYR');

    $key = $this->keys->keys[1];
    $rotated = $this->keys->all()[0];

    expect($response->getContent())->toContain('value="'.$key.'"')
        ->and($response->headers->get('Cache-Control'))->toContain('no-store')
        ->and($this->keys->calls)->toBe([['method' => 'rotate', 'argument' => $app->id]])
        ->and($rotated->revokedAt)->toBeNull();

    $row = DB::table('audit_logs')->sole();

    expect($row->action)->toBe('panel.app.key_rotated')
        ->and($row->subject_type)->toBe('app')
        ->and($row->subject_id)->toBe((string) $app->id)
        ->and(json_decode((string) $row->context, true))->toEqual(['nombre' => 'Portal RYR', 'prefijo' => $rotated->keyPrefix])
        ->and((string) $row->context)->not->toContain($key);
})->with([
    'active' => [null, 'Generar llave nueva'],
    'revoked' => ['2026-10-20 16:45', 'Reactivar con llave nueva'],
]);

it('answers 404 for an app that does not exist', function (string $action) {
    $this->actingAs($this->admin)->post("/panel/apps/99/{$action}")->assertNotFound();

    expect(DB::table('audit_logs')->count())->toBe(0);
})->with(['llave', 'revocar']);

it('only takes numeric app ids', function () {
    $this->actingAs($this->admin)->post('/panel/apps/portal/llave')->assertNotFound();

    expect($this->keys->calls)->toBe([]);
});

it('revokes the key of an app and says so', function () {
    $app = $this->keys->add('Portal RYR');

    $this->actingAs($this->admin)
        ->post(route('panel.apps.revoke', $app->id))
        ->assertRedirect(route('panel.apps'))
        ->assertSessionHas('status', 'Revocamos la llave de Portal RYR.');

    expect($this->keys->calls)->toBe([['method' => 'revoke', 'argument' => $app->id]])
        ->and($this->keys->all()[0]->revokedAt)->not->toBeNull();

    $row = DB::table('audit_logs')->sole();

    expect($row->action)->toBe('panel.app.revoked')
        ->and($row->subject_type)->toBe('app')
        ->and($row->subject_id)->toBe((string) $app->id)
        ->and(json_decode((string) $row->context, true))->toEqual(['nombre' => 'Portal RYR', 'prefijo' => $app->keyPrefix]);

    $this->actingAs($this->admin)->get('/panel/apps')->assertSee('Revocamos la llave de Portal RYR.')->assertSee('Reactivar con llave nueva');
});

it('does not audit revoking an app that is already revoked', function () {
    $app = $this->keys->add('Portal RYR', revokedAt: '2026-10-20 16:45');

    $this->actingAs($this->admin)
        ->post(route('panel.apps.revoke', $app->id))
        ->assertRedirect(route('panel.apps'))
        ->assertSessionHas('status', 'Revocamos la llave de Portal RYR.');

    expect($this->keys->calls)->toBe([])
        ->and(DB::table('audit_logs')->count())->toBe(0);
});
