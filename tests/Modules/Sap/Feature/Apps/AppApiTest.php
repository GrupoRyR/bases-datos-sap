<?php

use App\Modules\Sap\Contracts\ClientAppKeys;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Models\Run;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;

/*
| The API the apps call with their own key (docs/contrato-robot.md,
| section 7.4): ask for an update, follow it and show when data was updated.
*/

beforeEach(function () {
    Carbon::setTestNow(Carbon::parse('2026-10-26 10:00:00', 'America/Bogota'));
    $this->key = app(ClientAppKeys::class)->issue('Gestor de cartera')->key;
});

/** @return array<string, string> */
function bearer(string $key): array
{
    return ['Authorization' => "Bearer {$key}"];
}

/** @param  array<string, mixed>  $overrides */
function askBody(array $overrides = []): array
{
    return array_merge([
        'empresa' => 'SGX',
        'conjunto' => 'MAESTROS',
        'parte' => 'clientes',
        'solicitado_por' => ['correo' => 'Ana@Segurex.com', 'nombre' => 'Ana Ruiz'],
    ], $overrides);
}

it('creates a request with 201 and joins an identical one with 200', function () {
    $created = $this->postJson('/api/v1/solicitudes', askBody(), bearer($this->key))
        ->assertCreated()
        ->assertExactJson([
            'id' => DB::table('update_requests')->value('id'),
            'estado' => 'pendiente',
            'correr_desde' => '2026-10-26T10:00:00-05:00',
            'empresa' => 'SGX',
            'conjunto' => 'MAESTROS',
            'parte' => 'clientes',
        ]);

    $this->postJson('/api/v1/solicitudes', askBody(['solicitado_por' => ['correo' => 'luis@segurex.com']]), bearer($this->key))
        ->assertOk()
        ->assertJsonPath('id', $created->json('id'));

    $requesters = DB::table('update_request_requesters')->get();

    expect($requesters->pluck('correo')->all())->toBe(['ana@segurex.com', 'luis@segurex.com'])
        ->and($requesters->pluck('client_app_id')->unique()->all())->toBe([DB::table('client_apps')->value('id')]);
});

it('says when a request in a blocked slot runs', function () {
    Carbon::setTestNow(Carbon::parse('2026-10-26 11:50:00', 'America/Bogota'));

    $this->postJson('/api/v1/solicitudes', askBody(['conjunto' => 'CARTERA', 'parte' => null]), bearer($this->key))
        ->assertCreated()
        ->assertJsonPath('estado', 'en_cola')
        ->assertJsonPath('correr_desde', '2026-10-26T12:45:00-05:00')
        ->assertJsonPath('parte', null);
});

it('validates what an app asks for', function (array $overrides, string $field) {
    $this->postJson('/api/v1/solicitudes', askBody($overrides), bearer($this->key))
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor($field);
})->with([
    'unknown company' => [['empresa' => 'XYZ'], 'empresa'],
    'archive-only dataset' => [['conjunto' => 'AUDITORIA'], 'conjunto'],
    'part of CARTERA' => [['conjunto' => 'CARTERA', 'parte' => 'clientes'], 'parte'],
    'unknown part' => [['parte' => 'direcciones'], 'parte'],
    'no e-mail' => [['solicitado_por' => ['nombre' => 'Ana']], 'solicitado_por.correo'],
    'bad e-mail' => [['solicitado_por' => ['correo' => 'ana']], 'solicitado_por.correo'],
]);

it('refuses a missing, unknown or revoked key with 401', function () {
    $this->postJson('/api/v1/solicitudes', askBody())->assertUnauthorized()->assertExactJson(['message' => 'Llave inválida.']);
    $this->postJson('/api/v1/solicitudes', askBody(), bearer('bsap_otra'))->assertUnauthorized();

    app(ClientAppKeys::class)->revoke(DB::table('client_apps')->value('id'));

    $this->postJson('/api/v1/solicitudes', askBody(), bearer($this->key))->assertUnauthorized();
});

it('shows a request only to the apps that joined it', function () {
    $id = $this->postJson('/api/v1/solicitudes', askBody(), bearer($this->key))->json('id');
    DB::table('update_requests')->where('id', $id)->update([
        'estado' => 'fallida', 'tomada_en' => now(), 'terminada_en' => now(), 'error' => 'VPN no conectó',
    ]);

    $this->getJson("/api/v1/solicitudes/{$id}", bearer($this->key))
        ->assertOk()
        ->assertJson([
            'id' => $id,
            'estado' => 'fallida',
            'tomada_en' => '2026-10-26T10:00:00-05:00',
            'terminada_en' => '2026-10-26T10:00:00-05:00',
            'error' => 'VPN no conectó',
            'solicitada_en' => '2026-10-26T10:00:00-05:00',
        ]);

    $other = app(ClientAppKeys::class)->issue('Toma de pedidos')->key;

    $this->getJson("/api/v1/solicitudes/{$id}", bearer($other))->assertNotFound();
    $this->getJson('/api/v1/solicitudes/999', bearer($this->key))->assertNotFound();
});

it('tells when each part of a dataset was last applied', function () {
    $closed = fn (array $parts, string $appliedAt, Company $company = Company::Sgx) => Run::create([
        'conjunto' => Dataset::Maestros, 'empresa' => $company, 'tipo' => 'solicitud', 'partes' => $parts,
        'solicitudes' => [], 'extraida_en' => $appliedAt, 'estado' => 'cerrada', 'abierta_hasta' => $appliedAt,
        'robot_key' => 'r2026a', 'aplicada_en' => $appliedAt,
    ]);
    $closed(['clientes' => 'cambios', 'direcciones' => 'cambios'], '2026-10-26 08:00:00');
    $closed(['clientes' => 'cambios'], '2026-10-26 09:30:00');
    $closed(['articulos' => 'cambios'], '2026-10-26 09:45:00', Company::Sdc);

    $response = $this->getJson('/api/v1/estado?empresa=SGX&conjunto=MAESTROS', bearer($this->key))->assertOk();

    expect($response->json('empresa'))->toBe('SGX')
        ->and($response->json('partes.clientes.actualizado_en'))->toBe('2026-10-26T09:30:00-05:00')
        ->and($response->json('partes.direcciones.actualizado_en'))->toBe('2026-10-26T08:00:00-05:00')
        ->and($response->json('partes.articulos.actualizado_en'))->toBeNull()
        ->and($response->json('partes'))->toHaveCount(12);
});

it('validates the status query', function () {
    $this->getJson('/api/v1/estado?empresa=SGX&conjunto=VENTAS', bearer($this->key))
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('conjunto');
});

it('shows a key once and keeps only its hash', function () {
    $issued = app(ClientAppKeys::class)->issue('Panel de pruebas');
    $stored = DB::table('client_apps')->where('nombre', 'Panel de pruebas')->sole();

    expect($issued->key)->toStartWith('bsap_')
        ->and(strlen($issued->key))->toBeGreaterThan(40)
        ->and($stored->key_hash)->toBe(hash('sha256', $issued->key))
        ->and($stored->key_prefix)->toBe(substr($issued->key, 0, 12))
        ->and((array) $stored)->not->toContain($issued->key);
});

it('creates a key from the console and prints it once', function () {
    $this->artisan('sap:app', ['nombre' => 'Toma de pedidos'])
        ->expectsOutputToContain('bsap_')
        ->assertSuccessful();

    expect(DB::table('client_apps')->where('nombre', 'Toma de pedidos')->exists())->toBeTrue();
});
