<?php

use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\RequestScope;
use App\Modules\Sap\Contracts\UpdateRequests;
use App\Modules\Sap\Domain\Runs\RunState;
use App\Modules\Sap\Models\Run;
use App\Modules\Sap\Models\UpdateRequest;
use Illuminate\Support\Arr;
use Tests\Modules\Sap\Support\RobotClient;
use Tests\TestCase;

/*
| Starting a run (docs/contrato-robot.md, section 4.1).
*/

beforeEach(function () {
    RobotClient::configure();
    $this->freezeSecond();
});

/**
 * @param  array<string, mixed>  $overrides
 * @return array<string, mixed>
 */
function maestrosRequestRun(array $overrides = []): array
{
    return array_merge([
        'conjunto' => 'MAESTROS',
        'empresa' => 'SGX',
        'tipo' => 'solicitud',
        'partes' => ['clientes' => 'cambios', 'direcciones' => 'cambios', 'contactos' => 'cambios'],
        'solicitudes' => [],
        'fecha_corte' => null,
        'extraida_en' => '2026-10-23T10:41:30-05:00',
    ], $overrides);
}

/** @return array<string, string> Every MAESTROS part in mode "todo", as a full run sends them. */
function allMaestrosInFull(): array
{
    return array_fill_keys([
        'clientes', 'proveedores', 'direcciones', 'contactos', 'articulos', 'grupos_articulos', 'marcas',
        'precios', 'vendedores', 'grupos_clientes', 'condiciones_pago', 'municipios',
    ], 'todo');
}

it('opens a run and answers when it closes for lack of batches', function () {
    $response = RobotClient::post($this, '/api/robot/v1/corridas', maestrosRequestRun())->assertCreated();

    $run = Run::sole();

    $response->assertExactJson([
        'run_id' => $run->id,
        'estado' => 'abierta',
        'abierta_hasta' => now()->addMinutes(30)->toIso8601String(),
    ]);

    expect($run->estado)->toBe(RunState::Open)
        ->and($run->partes)->toEqual(['clientes' => 'cambios', 'direcciones' => 'cambios', 'contactos' => 'cambios'])
        ->and($run->robot_key)->toBe(RobotClient::KEY)
        ->and($run->extraida_en->toIso8601String())->toBe('2026-10-23T10:41:30-05:00');
});

it('opens the nightly full runs of both datasets', function () {
    RobotClient::post($this, '/api/robot/v1/corridas', maestrosRequestRun(['tipo' => 'completa', 'partes' => allMaestrosInFull()]))
        ->assertCreated();

    RobotClient::post($this, '/api/robot/v1/corridas', [
        'conjunto' => 'CARTERA', 'empresa' => 'SDC', 'tipo' => 'completa', 'partes' => ['cartera' => 'todo'],
        'solicitudes' => [], 'fecha_corte' => '2026-10-22', 'extraida_en' => '2026-10-23T02:05:00-05:00',
    ])->assertCreated();

    expect(Run::where('conjunto', 'CARTERA')->sole()->fecha_corte->toDateString())->toBe('2026-10-22');
});

it('lets Derivados leave the prices out of its full run, since it has no public price list', function () {
    RobotClient::post($this, '/api/robot/v1/corridas', maestrosRequestRun([
        'empresa' => 'SDC', 'tipo' => 'completa', 'partes' => Arr::except(allMaestrosInFull(), 'precios'),
    ]))->assertCreated();

    expect(Run::sole()->partes)->not->toHaveKey('precios')->toHaveCount(11);
});

/** @return array<string, string> The parts a whole MAESTROS request of Derivados brings when it has no prices. */
function maestrosWithoutPrices(): array
{
    return ['clientes' => 'cambios', 'proveedores' => 'cambios', 'direcciones' => 'cambios', 'contactos' => 'cambios', 'articulos' => 'cambios']
        + Arr::except(allMaestrosInFull(), ['clientes', 'proveedores', 'direcciones', 'contactos', 'articulos', 'precios']);
}

function takeMaestrosRequest(TestCase $test, Company $company, ?RequestScope $scope): int
{
    $id = app(UpdateRequests::class)->request($company, Dataset::Maestros, $scope, 'ana@segurex.com', 'Ana Ruiz')->id;
    RobotClient::post($test, '/api/robot/v1/solicitudes/tomar', ['max' => 20])->assertOk();

    return $id;
}

it('serves a whole MAESTROS request of Derivados without the prices it does not have', function () {
    $request = takeMaestrosRequest($this, Company::Sdc, null);

    RobotClient::post($this, '/api/robot/v1/corridas', maestrosRequestRun([
        'empresa' => 'SDC', 'partes' => maestrosWithoutPrices(), 'solicitudes' => [$request],
    ]))->assertCreated();

    expect(UpdateRequest::find($request)->run_id)->toBe(Run::sole()->id);
});

it('still needs the prices in the run for a request of just the prices of Derivados, so it is answered', function () {
    $request = takeMaestrosRequest($this, Company::Sdc, RequestScope::Prices);

    RobotClient::post($this, '/api/robot/v1/corridas', maestrosRequestRun([
        'empresa' => 'SDC', 'partes' => ['clientes' => 'cambios'], 'solicitudes' => [$request],
    ]))->assertUnprocessable()->assertJsonValidationErrorFor('solicitudes');

    RobotClient::post($this, '/api/robot/v1/corridas', maestrosRequestRun([
        'empresa' => 'SDC', 'partes' => ['precios' => 'todo'], 'solicitudes' => [$request],
    ]))->assertCreated();
});

it('still needs the prices in the run for a whole MAESTROS request of Segurex', function () {
    $request = takeMaestrosRequest($this, Company::Sgx, null);

    RobotClient::post($this, '/api/robot/v1/corridas', maestrosRequestRun([
        'partes' => maestrosWithoutPrices(), 'solicitudes' => [$request],
    ]))->assertUnprocessable()->assertJsonValidationErrorFor('solicitudes');
});

it('rejects what the contract does not allow with 422', function (array $overrides, string $field) {
    RobotClient::post($this, '/api/robot/v1/corridas', maestrosRequestRun($overrides))
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor($field);

    expect(Run::count())->toBe(0);
})->with([
    'unknown dataset' => [['conjunto' => 'VENTAS'], 'conjunto'],
    'unknown company' => [['empresa' => 'XYZ'], 'empresa'],
    'unknown type' => [['tipo' => 'parcial'], 'tipo'],
    'archive-only table' => [['partes' => ['auditoria' => 'todo']], 'partes.auditoria'],
    'part of the other dataset' => [['partes' => ['cartera' => 'todo']], 'partes.cartera'],
    'unknown mode' => [['partes' => ['clientes' => 'algunos']], 'partes.clientes'],
    'no parts' => [['partes' => []], 'partes'],
    'full run missing a part' => [['tipo' => 'completa', 'partes' => ['clientes' => 'todo']], 'partes'],
    'full run with changes' => [['tipo' => 'completa', 'partes' => ['clientes' => 'cambios'] + allMaestrosInFull()], 'partes.clientes'],
    'full run of Segurex without prices' => [['tipo' => 'completa', 'partes' => Arr::except(allMaestrosInFull(), 'precios')], 'partes'],
    'full run of Derivados without another part' => [['empresa' => 'SDC', 'tipo' => 'completa', 'partes' => Arr::except(allMaestrosInFull(), 'marcas')], 'partes'],
    'cut-off date in MAESTROS' => [['fecha_corte' => '2026-10-22'], 'fecha_corte'],
    'time without offset' => [['extraida_en' => '2026-10-23T10:41:30'], 'extraida_en'],
    'requests that are not ids' => [['solicitudes' => ['118']], 'solicitudes'],
]);

it('requires CARTERA to come whole and with its cut-off date', function (array $overrides, string $field) {
    RobotClient::post($this, '/api/robot/v1/corridas', array_merge([
        'conjunto' => 'CARTERA', 'empresa' => 'SGX', 'tipo' => 'solicitud', 'partes' => ['cartera' => 'todo'],
        'solicitudes' => [], 'fecha_corte' => '2026-10-23', 'extraida_en' => '2026-10-23T10:41:30-05:00',
    ], $overrides))->assertUnprocessable()->assertJsonValidationErrorFor($field);
})->with([
    'in changes' => [['partes' => ['cartera' => 'cambios']], 'partes.cartera'],
    'without cut-off date' => [['fecha_corte' => null], 'fecha_corte'],
    'invalid cut-off date' => [['fecha_corte' => '2026-02-30'], 'fecha_corte'],
]);

it('allows one open run per dataset and company', function () {
    $first = RobotClient::post($this, '/api/robot/v1/corridas', maestrosRequestRun())->json('run_id');

    RobotClient::post($this, '/api/robot/v1/corridas', maestrosRequestRun())
        ->assertConflict()
        ->assertJsonPath('run_id', $first);

    // Another company, or the other dataset, runs at the same time.
    RobotClient::post($this, '/api/robot/v1/corridas', maestrosRequestRun(['empresa' => 'SDC']))->assertCreated();
    RobotClient::post($this, '/api/robot/v1/corridas', [
        'conjunto' => 'CARTERA', 'empresa' => 'SGX', 'tipo' => 'solicitud', 'partes' => ['cartera' => 'todo'],
        'solicitudes' => [], 'fecha_corte' => '2026-10-23', 'extraida_en' => '2026-10-23T10:41:30-05:00',
    ])->assertCreated();
});

it('expires an idle open run instead of letting it block the next one', function () {
    $first = RobotClient::post($this, '/api/robot/v1/corridas', maestrosRequestRun())->json('run_id');

    $this->travel(31)->minutes();

    RobotClient::post($this, '/api/robot/v1/corridas', maestrosRequestRun())->assertCreated();

    expect(Run::find($first)->estado)->toBe(RunState::Expired);
});

it('accepts only signed requests', function () {
    $this->postJson('/api/robot/v1/corridas', maestrosRequestRun())->assertUnauthorized();
});
