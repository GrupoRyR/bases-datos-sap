<?php

use App\Modules\Sap\Contracts\ClientAppKeys;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Contracts\Enums\RequestScope;
use App\Modules\Sap\Contracts\Enums\RequestState;
use App\Modules\Sap\Contracts\UpdateRequests;
use App\Modules\Sap\Models\Run;
use App\Modules\Sap\Models\UpdateRequest;
use Illuminate\Support\Carbon;
use Tests\Modules\Sap\Support\RobotClient;

/*
| Update requests of VENTAS (docs/contrato-robot.md, sections 7.1 and 7.4):
| VENTAS is asked whole, like CARTERA, and its run brings the part ventas
| in mode todo, with no "desde" since ventas has no SAP update time.
*/

beforeEach(function () {
    RobotClient::configure();
    Carbon::setTestNow(Carbon::parse('2026-10-16 10:00:00', 'America/Bogota'));
    $this->key = app(ClientAppKeys::class)->issue('Comisiones')->key;
});

/** @param  array<string, mixed>  $overrides */
function askVentas(array $overrides = []): array
{
    return array_merge([
        'empresa' => 'SGX',
        'conjunto' => 'VENTAS',
        'parte' => null,
        'solicitado_por' => ['correo' => 'ana@segurex.com', 'nombre' => 'Ana Ruiz'],
    ], $overrides);
}

it('lets an app ask for VENTAS whole', function () {
    $this->postJson('/api/v1/solicitudes', askVentas(), ['Authorization' => "Bearer {$this->key}"])
        ->assertCreated()
        ->assertJsonPath('conjunto', 'VENTAS')
        ->assertJsonPath('parte', null)
        ->assertJsonPath('estado', 'pendiente');
});

it('refuses any part of VENTAS', function (string $part) {
    $this->postJson('/api/v1/solicitudes', askVentas(['parte' => $part]), ['Authorization' => "Bearer {$this->key}"])
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('parte');
})->with(['ventas', 'clientes', 'catalogos']);

it('lets the panel ask for VENTAS whole and never by scope', function () {
    $requests = app(UpdateRequests::class);

    expect($requests->request(Company::Sdc, Dataset::Ventas, null, 'ana@segurex.com', 'Ana Ruiz')->dataset)->toBe(Dataset::Ventas)
        ->and(RequestScope::forDataset(Dataset::Ventas))->toBe([])
        ->and(RequestScope::partsFor(Dataset::Ventas, null))->toBe([Part::Sales])
        ->and(fn () => $requests->request(Company::Sdc, Dataset::Ventas, RequestScope::Customers, 'ana@segurex.com', null))
        ->toThrow(InvalidArgumentException::class);
});

it('is taken without desde and finished by the VENTAS run that serves it', function () {
    $id = app(UpdateRequests::class)->request(Company::Sgx, Dataset::Ventas, null, 'ana@segurex.com', 'Ana Ruiz')->id;

    RobotClient::post($this, '/api/robot/v1/solicitudes/tomar', ['max' => 20])
        ->assertOk()
        ->assertJsonPath('solicitudes.0.id', $id)
        ->assertJsonPath('solicitudes.0.conjunto', 'VENTAS')
        ->assertJsonPath('solicitudes.0.desde', []);

    $run = (int) RobotClient::post($this, '/api/robot/v1/corridas', [
        'conjunto' => 'VENTAS', 'empresa' => 'SGX', 'tipo' => 'solicitud', 'partes' => ['ventas' => 'todo'],
        'solicitudes' => [$id], 'fecha_corte' => null, 'ventana_desde' => '2026-09-24', 'extraida_en' => '2026-10-16T09:58:00-05:00',
    ])->assertCreated()->json('run_id');

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch(1, Part::Sales, [
        RobotClient::row(Part::Sales, ['fecha_contabilizacion' => '2026-10-15']),
    ]))->assertCreated();
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['ventas' => 1]])->assertOk();

    expect(UpdateRequest::find($id)->estado)->toBe(RequestState::Done)
        ->and(UpdateRequest::find($id)->run_id)->toBe($run);
});

it('says when VENTAS was last updated', function () {
    Run::create([
        'conjunto' => 'VENTAS', 'empresa' => 'SGX', 'tipo' => 'solicitud', 'partes' => ['ventas' => 'todo'], 'solicitudes' => [],
        'ventana_desde' => '2026-09-24', 'extraida_en' => now(), 'estado' => 'cerrada', 'abierta_hasta' => now(),
        'robot_key' => RobotClient::KEY, 'aplicada_en' => now()->subHour(),
    ]);

    $this->getJson('/api/v1/estado?empresa=SGX&conjunto=VENTAS', ['Authorization' => "Bearer {$this->key}"])
        ->assertOk()
        ->assertExactJson(['empresa' => 'SGX', 'conjunto' => 'VENTAS', 'partes' => ['ventas' => ['actualizado_en' => '2026-10-16T09:00:00-05:00']]]);
});
