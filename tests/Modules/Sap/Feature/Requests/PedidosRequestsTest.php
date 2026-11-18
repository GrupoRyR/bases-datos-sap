<?php

use App\Modules\Sap\Contracts\ClientAppKeys;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Contracts\Enums\RequestScope;
use App\Modules\Sap\Contracts\Enums\RequestState;
use App\Modules\Sap\Contracts\UpdateRequests;
use App\Modules\Sap\Models\UpdateRequest;
use Illuminate\Support\Carbon;
use Tests\Modules\Sap\Support\RobotClient;

/*
| Update requests of PEDIDOS (docs/contrato-robot.md, sections 7.1 and 11.3):
| PEDIDOS is asked whole, like CARTERA and VENTAS, and its run brings the
| part pedidos in mode todo, with no "desde".
*/

beforeEach(function () {
    RobotClient::configure();
    Carbon::setTestNow(Carbon::parse('2026-11-17 10:00:00', 'America/Bogota'));
    $this->key = app(ClientAppKeys::class)->issue('Panel Consolidado')->key;
});

/** @param  array<string, mixed>  $overrides */
function askPedidos(array $overrides = []): array
{
    return array_merge([
        'empresa' => 'SDC',
        'conjunto' => 'PEDIDOS',
        'parte' => null,
        'solicitado_por' => ['correo' => 'ana@segurex.com', 'nombre' => 'Ana Ruiz'],
    ], $overrides);
}

it('lets an app ask for PEDIDOS whole and refuses any part', function () {
    $this->postJson('/api/v1/solicitudes', askPedidos(), ['Authorization' => "Bearer {$this->key}"])
        ->assertCreated()
        ->assertJsonPath('conjunto', 'PEDIDOS')
        ->assertJsonPath('parte', null);

    $this->postJson('/api/v1/solicitudes', askPedidos(['parte' => 'pedidos']), ['Authorization' => "Bearer {$this->key}"])
        ->assertUnprocessable()
        ->assertJsonPath('errors.parte.0', 'PEDIDOS se pide completo: parte debe ser null.');
});

it('brings the part pedidos for a request of PEDIDOS and never by scope', function () {
    expect(RequestScope::forDataset(Dataset::Pedidos))->toBe([])
        ->and(RequestScope::partsFor(Dataset::Pedidos, null))->toBe([Part::Orders]);
});

it('is taken without desde and finished by the PEDIDOS run that serves it', function () {
    $id = app(UpdateRequests::class)->request(Company::Sgx, Dataset::Pedidos, null, 'ana@segurex.com', 'Ana Ruiz')->id;

    RobotClient::post($this, '/api/robot/v1/solicitudes/tomar', ['max' => 20])
        ->assertOk()
        ->assertJsonPath('solicitudes.0.id', $id)
        ->assertJsonPath('solicitudes.0.conjunto', 'PEDIDOS')
        ->assertJsonPath('solicitudes.0.desde', []);

    $run = (int) RobotClient::post($this, '/api/robot/v1/corridas', [
        'conjunto' => 'PEDIDOS', 'empresa' => 'SGX', 'tipo' => 'solicitud', 'partes' => ['pedidos' => 'todo'],
        'solicitudes' => [$id], 'fecha_corte' => null, 'extraida_en' => '2026-11-17T09:58:00-05:00',
    ])->assertCreated()->json('run_id');

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch(1, Part::Orders, [RobotClient::row(Part::Orders)]))->assertCreated();
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['pedidos' => 1]])->assertOk();

    expect(UpdateRequest::find($id)->estado)->toBe(RequestState::Done)
        ->and(UpdateRequest::find($id)->run_id)->toBe($run);
});
