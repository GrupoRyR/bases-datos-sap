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
| Update requests of PRODUCCION (docs/contrato-robot.md, sections 7.1 and
| 12.3): SGX only, asked whole, and its run brings the six parts in mode
| todo, with no "desde".
*/

beforeEach(function () {
    RobotClient::configure();
    Carbon::setTestNow(Carbon::parse('2026-11-18 10:00:00', 'America/Bogota'));
    $this->key = app(ClientAppKeys::class)->issue('Panel Consolidado')->key;
});

/** @param  array<string, mixed>  $overrides */
function askProduccion(array $overrides = []): array
{
    return array_merge([
        'empresa' => 'SGX',
        'conjunto' => 'PRODUCCION',
        'parte' => null,
        'solicitado_por' => ['correo' => 'ana@segurex.com', 'nombre' => 'Ana Ruiz'],
    ], $overrides);
}

it('lets an app ask for PRODUCCION of SGX whole and refuses any part or SDC', function () {
    $this->postJson('/api/v1/solicitudes', askProduccion(), ['Authorization' => "Bearer {$this->key}"])
        ->assertCreated()
        ->assertJsonPath('conjunto', 'PRODUCCION')
        ->assertJsonPath('parte', null);

    $this->postJson('/api/v1/solicitudes', askProduccion(['parte' => 'produccion_costos']), ['Authorization' => "Bearer {$this->key}"])
        ->assertUnprocessable()
        ->assertJsonPath('errors.parte.0', 'PRODUCCION se pide completo: parte debe ser null.');

    $this->postJson('/api/v1/solicitudes', askProduccion(['empresa' => 'SDC']), ['Authorization' => "Bearer {$this->key}"])
        ->assertUnprocessable()
        ->assertJsonPath('errors.empresa.0', 'PRODUCCION es solo de SGX.');

    expect(UpdateRequest::count())->toBe(1);
});

it('never places a PRODUCCION request of SDC', function () {
    expect(fn () => app(UpdateRequests::class)->request(Company::Sdc, Dataset::Produccion, null, 'ana@segurex.com', null))
        ->toThrow(InvalidArgumentException::class);

    expect(UpdateRequest::count())->toBe(0);
});

it('brings the six parts for a request of PRODUCCION and never by scope', function () {
    expect(RequestScope::forDataset(Dataset::Produccion))->toBe([])
        ->and(RequestScope::partsFor(Dataset::Produccion, null))->toBe(Part::forDataset(Dataset::Produccion));
});

it('is taken without desde and finished by the PRODUCCION run that serves it', function () {
    $id = app(UpdateRequests::class)->request(Company::Sgx, Dataset::Produccion, null, 'ana@segurex.com', 'Ana Ruiz')->id;

    RobotClient::post($this, '/api/robot/v1/solicitudes/tomar', ['max' => 20])
        ->assertOk()
        ->assertJsonPath('solicitudes.0.id', $id)
        ->assertJsonPath('solicitudes.0.conjunto', 'PRODUCCION')
        ->assertJsonPath('solicitudes.0.desde', []);

    $parts = Part::forDataset(Dataset::Produccion);
    $run = (int) RobotClient::post($this, '/api/robot/v1/corridas', [
        'conjunto' => 'PRODUCCION', 'empresa' => 'SGX', 'tipo' => 'solicitud',
        'partes' => array_fill_keys(array_map(fn (Part $part): string => $part->value, $parts), 'todo'),
        'solicitudes' => [$id], 'fecha_corte' => null, 'ventana_desde' => '2026-10-25', 'extraida_en' => '2026-11-18T09:58:00-05:00',
    ])->assertCreated()->json('run_id');

    foreach ($parts as $index => $part) {
        $row = RobotClient::row($part, $part->windowColumn() === null ? [] : [$part->windowColumn() => '2026-11-02']);
        RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch($index + 1, $part, [$row]))->assertCreated();
    }

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", [
        'batches' => count($parts),
        'filas' => array_fill_keys(array_map(fn (Part $part): string => $part->value, $parts), 1),
    ])->assertOk();

    expect(UpdateRequest::find($id)->estado)->toBe(RequestState::Done)
        ->and(UpdateRequest::find($id)->run_id)->toBe($run);
});
